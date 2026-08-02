import pytest
from pydantic import ValidationError

from app.mcp_server.schemas import PublishPayload


def valid_payload() -> dict:
    return {
        "idempotencyKey": "wx-20260802-agent-news",
        "topic": "Agent新闻",
        "kind": "news",
        "requestSummary": "整理并保存今天的重要Agent新闻",
        "items": [
            {
                "title": "Agent框架发布新版本",
                "summary": "新版本改进了工具调用。",
                "url": "https://example.com/release",
                "source": "Example",
                "keywords": ["Agent"],
                "reason": "与关注方向相关",
                "importance": 0.9,
            }
        ],
    }


def test_publish_requires_items_or_briefing() -> None:
    payload = valid_payload()
    payload.pop("items")

    with pytest.raises(ValidationError, match="items与briefing至少提供一个"):
        PublishPayload.model_validate(payload)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", "not-a-url"])
def test_publish_rejects_non_http_source(url: str) -> None:
    payload = valid_payload()
    payload["items"][0]["url"] = url

    with pytest.raises(ValidationError):
        PublishPayload.model_validate(payload)


def test_publish_rejects_more_than_twenty_items() -> None:
    payload = valid_payload()
    payload["items"] = payload["items"] * 21

    with pytest.raises(ValidationError):
        PublishPayload.model_validate(payload)


def test_publish_accepts_camel_case_and_normalizes_keywords() -> None:
    payload = valid_payload()
    payload["items"][0]["keywords"] = [" Agent ", "Agent", "RAG"]

    parsed = PublishPayload.model_validate(payload)

    assert parsed.request_summary == "整理并保存今天的重要Agent新闻"
    assert parsed.items[0].keywords == ["Agent", "RAG"]


def test_publish_rejects_unknown_fields() -> None:
    payload = valid_payload()
    payload["requestSummery"] = "拼写错误的字段"

    with pytest.raises(ValidationError, match="requestSummery"):
        PublishPayload.model_validate(payload)
