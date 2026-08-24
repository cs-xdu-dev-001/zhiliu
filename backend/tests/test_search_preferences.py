from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mcp_server.schemas import PublishPayload
from app.mcp_server.service import PublicationService
from app.models import Briefing, HermesQualityDecision, IntelligenceItem, ItemRevision, ItemTopic
from app.services.item_maintenance import ItemMaintenanceService
from app.services.preferences import PreferenceService
from app.services.topics import ensure_topic


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


def test_search_only_returns_latest_report_version(
    client,
    db_session: Session,
    subscription,
) -> None:
    versions = [
        Briefing(subscription_id=subscription.id, title="Agent专题旧版", kind="news", content="Agent旧结论", item_count=1, series_id="search-series", version_number=1),
        Briefing(subscription_id=subscription.id, title="Agent专题新版", kind="news", content="Agent新结论", item_count=1, series_id="search-series", version_number=2),
    ]
    db_session.add_all(versions)
    db_session.commit()

    response = client.get("/api/search", params={"q": "Agent专题"})

    assert response.status_code == 200
    assert [report["id"] for report in response.json()["briefings"]] == [versions[1].id]
    assert response.json()["briefingTotal"] == 1


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


def test_latest_source_preference_replaces_opposite_effect(client) -> None:
    preferred = client.post(
        "/api/preferences",
        json={"scope": "source", "effect": "prefer", "value": "Example", "kind": "news"},
    )
    avoided = client.post(
        "/api/preferences",
        json={"scope": "source", "effect": "avoid", "value": "Example", "kind": "news"},
    )

    assert preferred.status_code == 201
    assert avoided.status_code == 201
    assert [(item["effect"], item["value"]) for item in client.get("/api/preferences").json()["items"]] == [
        ("avoid", "Example")
    ]


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


def test_low_importance_content_is_kept_with_explicit_quality_reason(db_session: Session) -> None:
    payload = PublishPayload.model_validate({
        "idempotencyKey": "low-importance-kept",
        "traceId": "trace-low-importance-kept",
        "topic": "边缘线索",
        "kind": "news",
        "requestSummary": "保留低优先级线索",
        "items": [{
            "title": "低优先级但可追溯的线索", "summary": "暂不重要，仍保留供后续核验",
            "url": "https://example.com/low-signal", "source": "Example", "importance": 0.2,
        }],
    })

    receipt = PublicationService(db_session).publish(payload)
    decision = db_session.scalar(select(HermesQualityDecision))

    assert receipt.item_count == 1
    assert db_session.scalar(select(IntelligenceItem)) is not None
    assert decision is not None
    assert decision.reason_code == "low_importance"
    assert decision.reason == "重要性低于40分，已写入但降低展示优先级"


def test_hermes_feedback_updates_item_and_keeps_revision(
    db_session: Session,
    seeded_item,
) -> None:
    record = ItemMaintenanceService(db_session).apply_feedback(
        seeded_item.id,
        summary="重新整理后的摘要",
        priority="lower",
        ignored=True,
        source_unavailable=True,
    )

    assert record.summary == "重新整理后的摘要"
    assert record.importance == 0.3
    assert record.is_ignored is True
    assert record.source_unavailable is True
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


def test_quality_overview_counts_actionable_content_states(client, db_session: Session, subscription) -> None:
    record = IntelligenceItem(
        subscription_id=subscription.id,
        kind="news",
        title="需要复核的旧线索",
        summary="同时属于可能过期、低优先级和原文失效",
        url="https://example.com/actionable-quality",
        source="Example",
        published_at=datetime.now(timezone.utc) - timedelta(days=31),
        keywords_json="[]",
        importance=0.2,
        fingerprint="f" * 64,
        source_unavailable=True,
    )
    db_session.add(record)
    db_session.commit()

    payload = client.get("/api/quality").json()

    assert payload["staleCount"] == 1
    assert payload["lowImportanceCount"] == 1
    assert payload["sourceUnavailableCount"] == 1


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


def test_personalization_ranking_is_consistent_across_home_feed_and_topic(
    client,
    db_session: Session,
    subscription,
    seeded_item,
) -> None:
    seeded_item.importance = 0.72
    competitor = IntelligenceItem(
        subscription_id=subscription.id,
        kind="news",
        title="通用模型产业动态",
        summary="重要但不匹配明确偏好。",
        url="https://example.com/general-model",
        source="Other Research",
        keywords_json='["Agent"]',
        importance=0.8,
        fingerprint="b" * 64,
    )
    topic = ensure_topic(db_session, "Agent")
    db_session.add(competitor)
    db_session.flush()
    db_session.add_all([
        ItemTopic(item_id=seeded_item.id, topic_id=topic.id),
        ItemTopic(item_id=competitor.id, topic_id=topic.id),
    ])
    db_session.commit()

    created = client.post(
        "/api/preferences",
        json={"scope": "source", "effect": "prefer", "value": "Example Research", "kind": "all"},
    )

    assert created.status_code == 201
    feed = client.get("/api/items", params={"state": "unread", "sort": "importance"}).json()
    home = client.get("/api/dashboard").json()
    topic_detail = client.get(f"/api/topics/{topic.id}").json()
    assert feed["items"][0]["id"] == seeded_item.id
    assert home["topItems"][0]["id"] == seeded_item.id
    assert topic_detail["latestItems"][0]["id"] == seeded_item.id
    assert feed["items"][0]["personalizedScore"] == 0.84
    assert feed["items"][0]["recommendationReasons"][0]["code"] == "source_prefer"


def test_auto_learning_can_be_disabled_without_losing_explicit_preferences(
    client,
    seeded_item,
) -> None:
    client.post(
        "/api/preferences",
        json={"scope": "source", "effect": "prefer", "value": "Example Research", "kind": "all"},
    )
    updated = client.patch(
        f"/api/items/{seeded_item.id}",
        json={"isRead": True, "isSaved": True, "isIgnored": True},
    ).json()

    reason_codes = {reason["code"] for reason in updated["recommendationReasons"]}
    assert "ignored" in reason_codes
    assert "saved" not in reason_codes
    assert "read" not in reason_codes

    disabled = client.put(
        "/api/preferences/personalization",
        json={"autoLearningEnabled": False},
    )
    restored = client.get(f"/api/items/{seeded_item.id}").json()

    assert disabled.status_code == 200
    assert disabled.json()["autoLearningEnabled"] is False
    assert restored["personalizedScore"] == 1.0
    assert [reason["code"] for reason in restored["recommendationReasons"]] == ["source_prefer"]


def test_removed_preference_can_be_restored_with_previous_ranking_effect(
    client,
    seeded_item,
) -> None:
    created = client.post(
        "/api/preferences",
        json={"scope": "source", "effect": "avoid", "value": "Example Research", "kind": "all"},
    ).json()
    reduced = client.get(f"/api/items/{seeded_item.id}").json()["personalizedScore"]

    client.delete(f"/api/preferences/{created['id']}")
    base = client.get(f"/api/items/{seeded_item.id}").json()["personalizedScore"]
    restored = client.post(f"/api/preferences/{created['id']}/restore")
    reduced_again = client.get(f"/api/items/{seeded_item.id}").json()["personalizedScore"]

    assert reduced == 0.72
    assert base == 0.92
    assert restored.status_code == 200
    assert reduced_again == reduced


def test_content_specific_preference_does_not_affect_other_kinds(client, seeded_item) -> None:
    client.post(
        "/api/preferences",
        json={"scope": "source", "effect": "avoid", "value": "Example Research", "kind": "paper"},
    )

    item = client.get(f"/api/items/{seeded_item.id}").json()

    assert item["kind"] == "news"
    assert item["personalizedScore"] == seeded_item.importance
    assert all(reason["code"] != "source_avoid" for reason in item["recommendationReasons"])
