from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mcp_server.schemas import PublishPayload
from app.mcp_server.service import PublicationService
from app.models import Briefing, IntelligenceItem, ItemRevision
from app.services.item_maintenance import ItemMaintenanceService
from app.services.preferences import PreferenceService


def test_natural_language_search_finds_items_and_reports(
    client,
    db_session: Session,
    subscription,
    seeded_item,
) -> None:
    report = Briefing(
        subscription_id=subscription.id,
        title="Agent框架趋势报告",
        kind="news",
        content="总结工具调用与上下文管理的共同变化。",
        item_count=1,
    )
    db_session.add(report)
    db_session.commit()

    response = client.get("/api/search", params={"q": "最近有哪些Agent框架更新"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "最近有哪些Agent框架更新"
    assert payload["items"][0]["id"] == seeded_item.id
    assert payload["briefings"][0]["id"] == report.id
    assert payload["itemTotal"] == 1
    assert payload["briefingTotal"] == 1


def test_preferences_can_be_saved_listed_and_removed(client) -> None:
    created = client.post(
        "/api/preferences",
        json={
            "scope": "source",
            "effect": "avoid",
            "value": "低质量来源",
            "kind": "news",
            "note": "用户要求以后不要收录",
        },
    )
    repeated = client.post(
        "/api/preferences",
        json={
            "scope": "source",
            "effect": "avoid",
            "value": "低质量来源",
            "kind": "news",
            "note": "已确认",
        },
    )

    assert created.status_code == 201
    assert repeated.json()["id"] == created.json()["id"]
    listed = client.get("/api/preferences").json()["items"]
    assert len(listed) == 1
    assert listed[0]["note"] == "已确认"

    removed = client.delete(f"/api/preferences/{created.json()['id']}")
    assert removed.status_code == 200
    assert removed.json()["active"] is False
    assert client.get("/api/preferences").json()["items"] == []


def test_source_avoidance_is_enforced_during_publication(db_session: Session) -> None:
    PreferenceService(db_session).save(
        scope="source",
        effect="avoid",
        value="Blocked Source",
        kind="news",
    )
    payload = PublishPayload.model_validate(
        {
            "idempotencyKey": "preference-filtered",
            "traceId": "trace-preference-filtered",
            "topic": "过滤来源",
            "kind": "news",
            "requestSummary": "不要收录低质量来源",
            "items": [
                {
                    "title": "应被过滤",
                    "summary": "不会写入",
                    "url": "https://example.com/blocked",
                    "source": "Blocked Source",
                    "importance": 0.8,
                }
            ],
        }
    )

    receipt = PublicationService(db_session).publish(payload)

    assert receipt.item_count == 0
    assert receipt.skipped_count == 0
    assert receipt.filtered_count == 1
    assert db_session.scalar(select(IntelligenceItem)) is None


def test_hermes_feedback_updates_item_and_keeps_revision(
    db_session: Session,
    seeded_item,
) -> None:
    record = ItemMaintenanceService(db_session).apply_feedback(
        seeded_item.id,
        summary="重新整理后的摘要",
        priority="lower",
        ignored=True,
    )

    assert record.summary == "重新整理后的摘要"
    assert record.importance == 0.3
    assert record.is_ignored is True
    revision = db_session.scalar(select(ItemRevision))
    assert revision.action == "hermes_feedback"
    assert "重新整理后的摘要" in revision.after_json


def test_quality_center_exposes_reason_and_can_restore_filtered_content(client, db_session: Session) -> None:
    PreferenceService(db_session).save(scope="source", effect="avoid", value="Blocked", kind="news")
    payload = PublishPayload.model_validate({
        "idempotencyKey": "quality-center-test",
        "traceId": "trace-quality-center-test",
        "topic": "质量中心",
        "kind": "news",
        "requestSummary": "检查过滤理由",
        "items": [{"title": "被过滤内容", "summary": "可以恢复", "url": "https://example.com/quality", "source": "Blocked", "importance": 0.7}],
    })
    receipt = PublicationService(db_session).publish(payload)
    listed = client.get("/api/quality", params={"action": "filtered"})
    assert listed.status_code == 200
    decision = listed.json()["items"][0]
    assert decision["reasonCode"] == "source_avoid"
    restored = client.post(f"/api/quality/{decision['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["restoredAt"] is not None
    assert client.get("/api/quality", params={"action": "filtered"}).json()["items"] == []
    restored_items = client.get("/api/quality", params={"action": "restored"}).json()["items"]
    assert [item["id"] for item in restored_items] == [decision["id"]]
    assert client.get(f"/api/items/{restored.json()['itemId']}").status_code == 200


def test_subscription_health_summarizes_recent_runs(client, db_session: Session, subscription) -> None:
    from app.models import TaskRun

    db_session.add_all([
        TaskRun(subscription_id=subscription.id, status="success", stage="completed", duration_ms=1200),
        TaskRun(subscription_id=subscription.id, status="failed", stage="failed", error_message="超时"),
    ])
    db_session.commit()
    response = client.get("/api/subscription-health")
    assert response.status_code == 200
    item = next(value for value in response.json()["items"] if value["subscriptionId"] == subscription.id)
    assert item["runCount"] == 2
    assert item["successRate"] == 0.5
    assert item["consecutiveFailures"] == 1
