import asyncio
import json
import time
from datetime import datetime

import httpx
from pydantic import ValidationError

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


class HermesError(RuntimeError):
    pass


class HermesUnavailable(HermesError):
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
        owns_client = self._external_client is None
        client = self._external_client or httpx.AsyncClient(timeout=httpx.Timeout(10, read=30))
        try:
            started = await client.post(
                f"{self.base_url}/v1/runs",
                headers=self._headers,
                json={"input": prompt, "instructions": OUTPUT_INSTRUCTIONS},
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
                    return self._parse_result(run_id, state.get("output", ""))
                if status in {"failed", "cancelled"}:
                    raise HermesError(state.get("error") or f"Hermes run {status}")
                await asyncio.sleep(self.poll_interval)
            raise HermesTimeout(f"Hermes任务超过{self.timeout_seconds:g}秒")
        except HermesError:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise HermesUnavailable(f"Hermes API不可用: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _parse_result(run_id: str, raw_output: str) -> HermesResult:
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```")
            cleaned = cleaned.removesuffix("```").strip()
        try:
            payload = HermesPayload.model_validate_json(cleaned)
        except (ValidationError, ValueError) as exc:
            raise HermesInvalidOutput(f"Hermes返回内容不符合知流JSON协议: {exc}") from exc
        return HermesResult(
            run_id=run_id,
            briefing=payload.briefing,
            items=payload.items,
            raw_output=raw_output,
        )

