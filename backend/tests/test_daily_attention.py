import pytest
from sqlalchemy.orm import Session

from app.models import Briefing, IntelligenceItem, ItemChange, ItemTopic, TaskRun
from app.services.hermes import HermesTimeout
from app.services.report_service import ReportService
from app.services.topics import ensure_topic


class TimeoutReportClient:
    async def execute_report(self, prompt: str):
        raise HermesTimeout("Hermes生成超时")


def test_daily_attention_queues_once_for_same_day_and_scope(client, seeded_item) -> None:
    snapshot = client.get("/api/daily-attention")

    assert snapshot.status_code == 200
    assert snapshot.json()["items"][0]["item"]["id"] == seeded_item.id
    assert snapshot.json()["items"][0]["reasons"] == ["高价值新增"]

    first = client.post("/api/daily-attention/generate")
    repeated = client.post("/api/daily-attention/generate")

    assert first.status_code == 202
    assert first.json()["created"] is True
    assert first.json()["task"]["topic"] == "每日关注摘要"
    assert repeated.status_code == 202
    assert repeated.json()["created"] is False
    assert repeated.json()["task"]["id"] == first.json()["task"]["id"]


def test_daily_attention_does_not_create_empty_report(client, db_session: Session, seeded_item) -> None:
    seeded_item.importance = 0.2
    seeded_item.personalized_score = 0.2
    db_session.commit()

    response = client.post("/api/daily-attention/generate")

    assert response.status_code == 202
    assert response.json() == {
        "created": False,
        "message": "今日没有达到条件的重要变化，未生成空摘要",
        "task": None,
    }
    assert db_session.query(TaskRun).filter_by(topic="每日关注摘要").count() == 0


def test_daily_attention_settings_control_minimum_importance(client, seeded_item) -> None:
    response = client.put(
        "/api/daily-attention/settings",
        json={"minImportance": 0.95, "importantOnly": False},
    )

    assert response.status_code == 200
    assert response.json()["settings"] == {"minImportance": 0.95, "importantOnly": False}
    assert response.json()["items"] == []


def test_followed_topics_limit_ordinary_new_content(client, db_session: Session, subscription, seeded_item) -> None:
    topic = ensure_topic(db_session, "重点主题")
    topic.is_followed = True
    focused = IntelligenceItem(
        subscription_id=subscription.id,
        kind="news",
        title="重点主题的新进展",
        summary="属于明确关注范围。",
        url="https://example.com/focused",
        source="Example",
        keywords_json="[]",
        importance=0.85,
        fingerprint="e" * 64,
    )
    db_session.add(focused)
    db_session.flush()
    db_session.add(ItemTopic(item_id=focused.id, topic_id=topic.id))
    db_session.commit()

    item_ids = [row["item"]["id"] for row in client.get("/api/daily-attention").json()["items"]]

    assert focused.id in item_ids
    assert seeded_item.id not in item_ids


def test_daily_attention_combines_rising_topics_failures_and_pending_changes(
    client,
    db_session: Session,
    subscription,
    seeded_item,
) -> None:
    topic = ensure_topic(db_session, "Agent")
    topic.is_followed = True
    extra = IntelligenceItem(
        subscription_id=subscription.id,
        kind="news",
        title="Agent运行时更新",
        summary="新增可观测能力。",
        url="https://example.com/runtime-update",
        source="Example",
        keywords_json='["Agent"]',
        importance=0.82,
        fingerprint="d" * 64,
    )
    seeded_item.source_unavailable = True
    db_session.add(extra)
    db_session.flush()
    db_session.add_all([
        ItemTopic(item_id=seeded_item.id, topic_id=topic.id),
        ItemTopic(item_id=extra.id, topic_id=topic.id),
        ItemChange(
            item_id=seeded_item.id,
            change_type="important_update",
            basis="缺少上一条关联，等待确认",
            source_urls_json='["https://example.com/agent-release"]',
            before_json="{}",
            after_json="{}",
            status="pending",
            idempotency_key="pending-daily-attention",
        ),
        TaskRun(subscription_id=subscription.id, status="failed", stage="failed"),
        TaskRun(subscription_id=subscription.id, status="failed", stage="failed"),
    ])
    db_session.commit()

    payload = client.get("/api/daily-attention").json()

    assert payload["risingTopics"][0]["name"] == "Agent"
    assert payload["importantChangeCount"] == 1
    assert payload["sourceUnavailableCount"] == 1
    assert payload["pendingChangeCount"] == 1
    assert payload["consecutiveFailureCount"] == 1
    reasons = next(row["reasons"] for row in payload["items"] if row["item"]["id"] == seeded_item.id)
    assert set(reasons) == {"高价值新增", "重要变化", "来源失效", "待确认关联", "关注主题升温"}


@pytest.mark.asyncio
async def test_daily_attention_timeout_keeps_previous_valid_briefing(client, db_session: Session, seeded_item) -> None:
    previous_task = TaskRun(
        subscription_id=seeded_item.subscription_id,
        trace_id="daily-attention:previous",
        origin="web-report",
        topic="每日关注摘要",
        status="success",
        stage="completed",
    )
    db_session.add(previous_task)
    db_session.flush()
    previous = Briefing(
        subscription_id=seeded_item.subscription_id,
        title="上一份有效关注摘要",
        kind="news",
        content="有效结论[1]",
        item_count=1,
        series_id="previous-daily-attention",
        version_number=1,
        generation_task_id=previous_task.id,
        citation_status="valid",
    )
    db_session.add(previous)
    db_session.commit()
    queued = client.post("/api/daily-attention/generate").json()["task"]

    await ReportService(db_session, TimeoutReportClient()).execute_task(queued["id"])

    current_task = db_session.get(TaskRun, queued["id"])
    assert current_task.status == "queued"
    assert current_task.retry_count == 1
    assert db_session.query(Briefing).filter(Briefing.id != previous.id).count() == 0
    assert db_session.get(Briefing, previous.id).content == "有效结论[1]"
