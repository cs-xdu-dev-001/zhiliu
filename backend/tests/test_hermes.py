import json
from importlib import import_module

import httpx
import pytest


def _result_payload() -> dict:
    return {
        "briefing": {
            "title": "Agent论文周报",
            "kind": "paper",
            "content": "本周关注工具调用可靠性。",
            "periodStart": "2026-07-20T00:00:00Z",
            "periodEnd": "2026-07-27T00:00:00Z",
        },
        "items": [
            {
                "kind": "paper",
                "title": "Reliable Tool Use for Agents",
                "summary": "研究Agent工具调用的失败恢复。",
                "url": "https://arxiv.org/abs/2608.00001",
                "source": "arXiv",
                "publishedAt": "2026-07-25T00:00:00Z",
                "keywords": ["Agent", "Tool Use"],
                "reason": "与当前Agent工程主线相关",
                "importance": 0.91,
            }
        ],
    }


@pytest.mark.asyncio
async def test_execute_polls_run_and_parses_structured_result() -> None:
    hermes = import_module("app.services.hermes")
    polls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["input"] == "find papers"
            return httpx.Response(202, json={"run_id": "run_1", "status": "started"})
        polls += 1
        if polls == 1:
            return httpx.Response(200, json={"run_id": "run_1", "status": "running"})
        return httpx.Response(
            200,
            json={"run_id": "run_1", "status": "completed", "output": json.dumps(_result_payload())},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = hermes.HermesClient(
            base_url="http://hermes.local",
            api_key="test-key",
            timeout_seconds=2,
            poll_interval=0,
            http_client=http_client,
        )
        result = await client.execute("find papers")

    assert result.run_id == "run_1"
    assert result.briefing.title == "Agent论文周报"
    assert result.items[0].url == "https://arxiv.org/abs/2608.00001"


@pytest.mark.asyncio
async def test_execute_rejects_malformed_output() -> None:
    hermes = import_module("app.services.hermes")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, json={"run_id": "run_bad", "status": "started"})
        return httpx.Response(200, json={"run_id": "run_bad", "status": "completed", "output": "not-json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = hermes.HermesClient(
            base_url="http://hermes.local",
            api_key="test-key",
            timeout_seconds=2,
            poll_interval=0,
            http_client=http_client,
        )
        with pytest.raises(hermes.HermesInvalidOutput):
            await client.execute("bad output")


@pytest.mark.asyncio
async def test_execute_stops_remote_run_before_timeout() -> None:
    hermes = import_module("app.services.hermes")
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(f"{request.method} {request.url.path}")
        if request.method == "POST" and request.url.path == "/v1/runs":
            return httpx.Response(202, json={"run_id": "run_timeout", "status": "started"})
        if request.method == "GET":
            return httpx.Response(200, json={"run_id": "run_timeout", "status": "running"})
        assert request.method == "POST"
        assert request.url.path == "/v1/runs/run_timeout/stop"
        return httpx.Response(200, json={"status": "stopping"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = hermes.HermesClient(
            base_url="http://hermes.local", api_key="test-key", timeout_seconds=0,
            poll_interval=0, http_client=http_client,
        )
        with pytest.raises(hermes.HermesTimeout, match="超过0秒"):
            await client.execute("timeout")

    assert paths[-1] == "POST /v1/runs/run_timeout/stop"


@pytest.mark.asyncio
async def test_draft_subscription_parses_editable_configuration() -> None:
    hermes = import_module("app.services.hermes")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = json.loads(request.content)
            assert "订阅配置助手" in body["instructions"]
            return httpx.Response(202, json={"run_id": "draft_1", "status": "started"})
        return httpx.Response(200, json={
            "run_id": "draft_1",
            "status": "completed",
            "output": json.dumps({
                "subscription": {
                    "name": "Agent论文雷达",
                    "kind": "paper",
                    "keywords": ["Agent"],
                    "schedule": "0 8 * * *",
                    "prompt": "检索过去7天的Agent论文",
                    "enabled": True,
                },
                "explanation": "根据研究主题生成论文订阅",
                "assumptions": ["未指定时间，默认每天08:00"],
            }),
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = hermes.HermesClient(base_url="http://hermes.local", api_key="test-key", timeout_seconds=2, poll_interval=0, http_client=http_client)
        result = await client.draft_subscription("关注Agent论文")

    assert result.hermes_run_id == "draft_1"
    assert result.subscription.name == "Agent论文雷达"
    assert result.assumptions


@pytest.mark.asyncio
async def test_demo_draft_client_keeps_partial_fields() -> None:
    hermes = import_module("app.services.hermes")
    client = hermes.DemoSubscriptionDraftClient()

    result = await client.draft_subscription(json.dumps({
        "description": "跟踪Agent工程",
        "current": {"keywords": ["Agent"], "schedule": "0 9 * * 1"},
    }, ensure_ascii=False))

    assert result.subscription.keywords == ["Agent"]
    assert result.subscription.schedule == "0 9 * * 1"
    assert result.subscription.prompt


@pytest.mark.asyncio
async def test_execute_does_not_expose_remote_error_details() -> None:
    hermes = import_module("app.services.hermes")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, json={"run_id": "run_failed", "status": "started"})
        return httpx.Response(
            200,
            json={"run_id": "run_failed", "status": "failed", "error": "Bearer secret-value"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = hermes.HermesClient(
            base_url="http://hermes.local",
            api_key="test-key",
            timeout_seconds=2,
            poll_interval=0,
            http_client=http_client,
        )
        with pytest.raises(hermes.HermesError, match="Hermes任务执行失败") as failure:
            await client.execute("failed run")

    assert "secret-value" not in str(failure.value)


def test_item_fingerprint_normalizes_title_and_url() -> None:
    run_service = import_module("app.services.run_service")

    first = run_service.item_fingerprint(" Title ", "https://example.com/a/")
    second = run_service.item_fingerprint("title", "https://example.com/a")

    assert first == second
    assert len(first) == 64


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///etc/passwd", "not-a-url", "https://user:pass@example.com/"])
def test_item_fingerprint_rejects_unsafe_source_urls(url: str) -> None:
    run_service = import_module("app.services.run_service")
    with pytest.raises(ValueError, match="来源链接"):
        run_service.item_fingerprint("Title", url)


@pytest.mark.asyncio
async def test_probe_health_then_capabilities_with_auth() -> None:
    hermes = import_module("app.services.hermes")
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/health":
            return httpx.Response(200, json={"version": "1.2.3", "platform": "linux"})
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"capabilities": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = hermes.HermesClient(base_url="http://hermes.local", api_key="test-key", timeout_seconds=2, http_client=http_client)
        result = await client.probe()
    assert paths == ["/health", "/v1/capabilities"]
    assert result.version == "1.2.3"
    assert result.platform == "linux"


@pytest.mark.asyncio
async def test_probe_raises_unauthorized_on_capabilities_401() -> None:
    hermes = import_module("app.services.hermes")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={})
        return httpx.Response(401, json={"detail": "bad key"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = hermes.HermesClient(base_url="http://hermes.local", api_key="bad", timeout_seconds=2, http_client=http_client)
        with pytest.raises(hermes.HermesUnauthorized, match="Hermes拒绝了当前密钥"):
            await client.probe()

