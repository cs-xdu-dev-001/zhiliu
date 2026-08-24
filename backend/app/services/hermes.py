import asyncio
import json
import time
from datetime import datetime

import httpx
from pydantic import Field, ValidationError

from app.schemas import ApiModel, IntelligenceKind

OUTPUT_INSTRUCTIONS = """
只返回一个JSON对象，不要使用Markdown代码块。JSON必须符合以下结构：
{
  "briefing": {
    "title": "简报标题",
    "kind": "news|paper|job",
    "content": "综合简报正文",
    "periodStart": "ISO 8601时间或null",
    "periodEnd": "ISO 8601时间或null"
  },
  "items": [{
    "kind": "news|paper|job",
    "title": "标题",
    "summary": "中文摘要",
    "url": "原始链接",
    "source": "来源",
    "publishedAt": "ISO 8601时间或null",
    "keywords": ["关键词"],
    "reason": "推荐理由",
    "importance": 0.0
  }]
}
importance必须介于0和1之间，链接必须指向原始来源。
""".strip()

REPORT_OUTPUT_INSTRUCTIONS = """
只返回一个JSON对象，不要使用Markdown代码块。JSON必须符合以下结构：
{
  "title": "报告标题",
  "kind": "news|paper|job",
  "content": "带来源编号的完整中文报告正文"
}
正文中的事实必须使用输入资料对应的编号引用，例如[1]或[1][2]。不得捏造编号，不得引用输入之外的来源。
""".strip()


class HermesError(RuntimeError):
    pass


class HermesUnavailable(HermesError):
    pass


class HermesUnauthorized(HermesError):
    pass


class HermesTimeout(HermesError):
    pass


class HermesInvalidOutput(HermesError):
    pass


class HermesItem(ApiModel):
    kind: IntelligenceKind
    title: str
    summary: str
    url: str
    source: str
    published_at: datetime | None = None
    keywords: list[str]
    reason: str
    importance: float


class HermesBriefing(ApiModel):
    title: str
    kind: IntelligenceKind
    content: str
    period_start: datetime | None = None
    period_end: datetime | None = None


class HermesPayload(ApiModel):
    briefing: HermesBriefing
    items: list[HermesItem]


class HermesResult(ApiModel):
    run_id: str
    briefing: HermesBriefing
    items: list[HermesItem]
    raw_output: str


class HermesReport(ApiModel):
    run_id: str
    title: str = Field(min_length=1, max_length=300)
    kind: IntelligenceKind
    content: str = Field(min_length=1, max_length=100000)
    raw_output: str


class HermesProbe(ApiModel):
    version: str | None = None
    platform: str | None = None


class HermesClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        poll_interval: float = 1.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.poll_interval = poll_interval
        self._external_client = http_client
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def execute(self, prompt: str) -> HermesResult:
        run_id, raw_output = await self._execute_raw(prompt, OUTPUT_INSTRUCTIONS)
        return self._parse_result(run_id, raw_output)

    async def execute_report(self, prompt: str) -> HermesReport:
        run_id, raw_output = await self._execute_raw(prompt, REPORT_OUTPUT_INSTRUCTIONS)
        cleaned = self._clean_output(raw_output)
        try:
            payload = HermesReport.model_validate({"runId": run_id, "rawOutput": raw_output, **json.loads(cleaned)})
        except (ValidationError, ValueError, TypeError) as exc:
            raise HermesInvalidOutput("Hermes返回的报告不符合知流JSON协议") from exc
        return payload

    async def _execute_raw(self, prompt: str, instructions: str) -> tuple[str, str]:
        owns_client = self._external_client is None
        client = self._external_client or httpx.AsyncClient(timeout=httpx.Timeout(10, read=30))
        try:
            started = await client.post(
                f"{self.base_url}/v1/runs",
                headers=self._headers,
                json={"input": prompt, "instructions": instructions},
            )
            started.raise_for_status()
            run_id = started.json()["run_id"]
            deadline = time.monotonic() + self.timeout_seconds

            while time.monotonic() < deadline:
                response = await client.get(f"{self.base_url}/v1/runs/{run_id}", headers=self._headers)
                response.raise_for_status()
                state = response.json()
                status = state.get("status")
                if status == "completed":
                    return run_id, state.get("output", "")
                if status in {"failed", "cancelled"}:
                    message = "Hermes任务已取消" if status == "cancelled" else "Hermes任务执行失败"
                    raise HermesError(message)
                await asyncio.sleep(self.poll_interval)
            raise HermesTimeout(f"Hermes任务超过{self.timeout_seconds:g}秒")
        except HermesError:
            raise
        except httpx.HTTPStatusError as exc:
            raise HermesUnavailable(f"Hermes API返回HTTP {exc.response.status_code}") from exc
        except httpx.TimeoutException as exc:
            raise HermesUnavailable("Hermes API请求超时") from exc
        except httpx.HTTPError as exc:
            raise HermesUnavailable("Hermes API连接失败") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise HermesUnavailable("Hermes API响应格式错误") from exc
        finally:
            if owns_client:
                await client.aclose()

    async def probe(self) -> HermesProbe:
        owns_client = self._external_client is None
        client = self._external_client or httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds))
        try:
            health = await client.get(f"{self.base_url}/health")
            health.raise_for_status()
            health_data = health.json()
            if not isinstance(health_data, dict):
                raise ValueError("响应不是JSON对象")

            capabilities = await client.get(f"{self.base_url}/v1/capabilities", headers=self._headers)
            if capabilities.status_code in {401, 403}:
                raise HermesUnauthorized("Hermes拒绝了当前密钥")
            capabilities.raise_for_status()
            capabilities_data = capabilities.json()
            if not isinstance(capabilities_data, dict):
                raise ValueError("响应不是JSON对象")
            return HermesProbe.model_validate(health_data)
        except HermesUnauthorized:
            raise
        except httpx.HTTPStatusError as exc:
            raise HermesUnavailable(f"Hermes API返回HTTP {exc.response.status_code}") from exc
        except httpx.TimeoutException as exc:
            raise HermesUnavailable("Hermes API请求超时") from exc
        except httpx.HTTPError as exc:
            raise HermesUnavailable("Hermes API连接失败") from exc
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            raise HermesUnavailable("Hermes API响应格式错误") from exc
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _clean_output(raw_output: str) -> str:
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```")
            cleaned = cleaned.removesuffix("```").strip()
        return cleaned

    @staticmethod
    def _parse_result(run_id: str, raw_output: str) -> HermesResult:
        cleaned = HermesClient._clean_output(raw_output)
        try:
            payload = HermesPayload.model_validate_json(cleaned)
        except (ValidationError, ValueError) as exc:
            raise HermesInvalidOutput("Hermes返回内容不符合知流JSON协议") from exc
        return HermesResult(
            run_id=run_id,
            briefing=payload.briefing,
            items=payload.items,
            raw_output=raw_output,
        )

