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


def test_item_fingerprint_normalizes_title_and_url() -> None:
    run_service = import_module("app.services.run_service")

    first = run_service.item_fingerprint(" Title ", "https://example.com/a/")
    second = run_service.item_fingerprint("title", "https://example.com/a")

    assert first == second
    assert len(first) == 64

