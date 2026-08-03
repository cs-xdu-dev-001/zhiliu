from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import HermesPublication, IntelligenceItem, ItemRevision, PublicationItem
from app.services.run_service import item_fingerprint


def test_list_items_and_mark_read(client: TestClient, seeded_item) -> None:
    listed = client.get("/api/items?kind=news&state=unread")
    updated = client.patch(
        f"/api/items/{seeded_item.id}",
        json={"isRead": True},
    )

    assert listed.status_code == 200
    assert listed.json()["items"][0]["title"] == "Agent框架发布新版本"
    assert listed.json()["total"] == 1
    assert updated.status_code == 200
    assert updated.json()["isRead"] is True


def test_list_items_searches_visible_content(client: TestClient, seeded_item) -> None:
    by_title = client.get("/api/items", params={"state": "unread", "q": "Agent框架"})
    by_summary = client.get("/api/items", params={"state": "unread", "q": "上下文"})
    missing = client.get("/api/items", params={"state": "unread", "q": "不存在的关键词"})

    assert by_title.status_code == 200
    assert by_title.json()["total"] == 1
    assert by_summary.json()["total"] == 1
    assert missing.json()["total"] == 0


def test_list_items_treats_search_wildcards_as_text(client: TestClient, seeded_item) -> None:
    response = client.get("/api/items", params={"state": "unread", "q": "%"})

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_list_items_supports_stable_sorting(
    client: TestClient,
    db_session: Session,
    seeded_item,
    subscription,
) -> None:
    other = IntelligenceItem(
        subscription_id=subscription.id,
        kind="news",
        title="Beta更新",
        summary="第二条",
        url="https://example.com/beta",
        source="Example",
        keywords_json="[]",
        importance=0.1,
        fingerprint=item_fingerprint("Beta更新", "https://example.com/beta"),
    )
    db_session.add(other)
    db_session.commit()

    importance = client.get("/api/items", params={"state": "unread", "sort": "importance"}).json()
    title = client.get("/api/items", params={"state": "unread", "sort": "title"}).json()

    assert importance["items"][0]["id"] == seeded_item.id
    assert [item["title"] for item in title["items"]] == ["Agent框架发布新版本", "Beta更新"]


def test_bulk_item_action_updates_selected_items_and_reports_skips(
    client: TestClient,
    db_session: Session,
    seeded_item,
    subscription,
) -> None:
    merged = IntelligenceItem(
        subscription_id=subscription.id,
        kind="news",
        title="已合并审计记录",
        summary="只读",
        url="https://example.com/merged-audit",
        source="Example",
        keywords_json="[]",
        fingerprint=item_fingerprint("已合并审计记录", "https://example.com/merged-audit"),
        is_invalid=True,
        merged_into_id=seeded_item.id,
    )
    db_session.add(merged)
    db_session.commit()

    response = client.post(
        "/api/items/bulk",
        json={"ids": [seeded_item.id, merged.id, 999], "action": "save"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "requested": 3,
        "updated": 1,
        "skipped": [
            {"id": merged.id, "reason": "已合并，只读"},
            {"id": 999, "reason": "情报不存在"},
        ],
    }
    db_session.refresh(seeded_item)
    db_session.refresh(merged)
    assert seeded_item.is_saved is True
    assert merged.is_saved is False


def test_bulk_invalid_and_restore_record_revisions(client: TestClient, db_session: Session, seeded_item) -> None:
    invalidated = client.post(
        "/api/items/bulk",
        json={"ids": [seeded_item.id, seeded_item.id], "action": "invalidate"},
    )
    restored = client.post(
        "/api/items/bulk",
        json={"ids": [seeded_item.id], "action": "restore"},
    )

    assert invalidated.status_code == 200
    assert invalidated.json()["requested"] == 1
    assert invalidated.json()["updated"] == 1
    assert restored.json()["updated"] == 1
    assert [revision.action for revision in db_session.query(ItemRevision).order_by(ItemRevision.id)] == [
        "invalidated", "restored",
    ]


def test_bulk_action_validates_ids_and_action(client: TestClient) -> None:
    assert client.post("/api/items/bulk", json={"ids": [], "action": "save"}).status_code == 422
    assert client.post("/api/items/bulk", json={"ids": [1], "action": "delete"}).status_code == 422


def test_dashboard_reports_unread_count(client: TestClient, seeded_item) -> None:
    response = client.get("/api/dashboard")

    assert response.status_code == 200
    assert response.json()["unreadCount"] == 1
    assert response.json()["topItems"][0]["importance"] == 0.92


def test_dashboard_includes_recent_task_feedback(client: TestClient, db_session, subscription) -> None:
    from app.models import TaskRun

    task = TaskRun(
        subscription_id=subscription.id,
        trace_id="trace-dashboard-task",
        origin="weixin-hermes",
        topic="微信里的整理请求",
        request_summary="整理今天的重要更新",
        status="running",
        stage="processing",
    )
    db_session.add(task)
    db_session.commit()

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    assert response.json()["recentRuns"][0]["id"] == task.id
    assert response.json()["recentRuns"][0]["topic"] == "微信里的整理请求"


def test_missing_item_returns_not_found(client: TestClient) -> None:
    response = client.patch("/api/items/999", json={"isSaved": True})

    assert response.status_code == 404


def test_get_item_detail(client: TestClient, seeded_item) -> None:
    response = client.get(f"/api/items/{seeded_item.id}")

    assert response.status_code == 200
    assert response.json()["id"] == seeded_item.id
    assert response.json()["title"] == "Agent框架发布新版本"
    assert response.json()["reason"] == "影响Agent开发工作流"


def test_missing_item_detail_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/items/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "情报不存在"


def test_item_detail_includes_ordered_publication_records(
    client: TestClient,
    db_session: Session,
    seeded_item,
    subscription,
) -> None:
    publication = HermesPublication(
        idempotency_key="item-detail-trace",
        payload_hash="b" * 64,
        subscription_id=subscription.id,
        trace_id="trace-item-detail",
        hermes_run_id="hermes-item-detail",
        item_count=1,
        skipped_count=0,
        topic="Agent更新",
        request_summary="整理Agent更新并放进知流",
        origin="weixin-hermes",
    )
    db_session.add(publication)
    db_session.flush()
    db_session.add(
        PublicationItem(
            publication_id=publication.id,
            item_id=seeded_item.id,
            ordinal=0,
            was_inserted=True,
        )
    )
    db_session.commit()

    response = client.get(f"/api/items/{seeded_item.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["traceAvailable"] is True
    assert payload["publications"][0]["traceId"] == "trace-item-detail"
    assert payload["publications"][0]["hermesRunId"] == "hermes-item-detail"
    assert payload["publications"][0]["wasInserted"] is True


def test_historical_item_has_explicit_empty_trace(client: TestClient, seeded_item) -> None:
    response = client.get(f"/api/items/{seeded_item.id}")

    assert response.json()["traceAvailable"] is False
    assert response.json()["publications"] == []


def test_edit_item_content_recalculates_fingerprint_and_records_revision(
    client: TestClient,
    db_session: Session,
    seeded_item,
) -> None:
    old_fingerprint = seeded_item.fingerprint

    response = client.patch(
        f"/api/items/{seeded_item.id}/content",
        json={"title": "Agent框架关键更新", "summary": "人工修正后的摘要。", "kind": "paper"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Agent框架关键更新"
    assert response.json()["kind"] == "paper"
    db_session.refresh(seeded_item)
    assert seeded_item.fingerprint != old_fingerprint
    revision = db_session.query(ItemRevision).one()
    assert revision.action == "edited"
    assert '"title": "Agent框架发布新版本"' in revision.before_json
    assert '"title": "Agent框架关键更新"' in revision.after_json


def test_edit_item_rejects_existing_fingerprint(
    client: TestClient,
    db_session: Session,
    seeded_item,
    subscription,
) -> None:
    other = IntelligenceItem(
        subscription_id=subscription.id,
        kind="news",
        title="重复标题",
        summary="另一个摘要",
        url=seeded_item.url,
        source="Example",
        keywords_json="[]",
        fingerprint=item_fingerprint("重复标题", seeded_item.url),
    )
    db_session.add(other)
    db_session.commit()

    response = client.patch(
        f"/api/items/{seeded_item.id}/content",
        json={"title": "重复标题", "summary": "新摘要", "kind": "news"},
    )

    assert response.status_code == 409
    assert "合并" in response.json()["detail"]


def test_invalid_item_is_hidden_from_normal_feed_and_kept_in_invalid_filter(
    client: TestClient,
    db_session: Session,
    seeded_item,
) -> None:
    response = client.put(f"/api/items/{seeded_item.id}/validity", json={"invalid": True})

    assert response.status_code == 200
    assert response.json()["isInvalid"] is True
    assert client.get("/api/items?state=unread").json()["total"] == 0
    invalid = client.get("/api/items?state=invalid").json()
    assert invalid["total"] == 1
    assert invalid["items"][0]["id"] == seeded_item.id
    assert db_session.query(ItemRevision).one().action == "invalidated"


def test_merge_moves_publication_links_without_changing_snapshot_counts(
    client: TestClient,
    db_session: Session,
    seeded_item,
    subscription,
) -> None:
    target = IntelligenceItem(
        subscription_id=subscription.id,
        kind="news",
        title="Agent框架正式更新",
        summary="目标摘要",
        url="https://example.com/agent-release-canonical",
        source="Example",
        keywords_json="[]",
        fingerprint=item_fingerprint("Agent框架正式更新", "https://example.com/agent-release-canonical"),
    )
    db_session.add(target)
    db_session.flush()
    first = HermesPublication(
        idempotency_key="merge-first",
        payload_hash="c" * 64,
        subscription_id=subscription.id,
        item_count=2,
        skipped_count=0,
        topic="合并测试1",
        request_summary="合并测试1",
        origin="subscription-hermes",
    )
    second = HermesPublication(
        idempotency_key="merge-second",
        payload_hash="d" * 64,
        subscription_id=subscription.id,
        item_count=1,
        skipped_count=0,
        topic="合并测试2",
        request_summary="合并测试2",
        origin="subscription-hermes",
    )
    db_session.add_all([first, second])
    db_session.flush()
    seeded_item.is_invalid = True
    db_session.add_all([
        PublicationItem(publication_id=first.id, item_id=seeded_item.id, ordinal=0, was_inserted=True),
        PublicationItem(publication_id=first.id, item_id=target.id, ordinal=1, was_inserted=False),
        PublicationItem(publication_id=second.id, item_id=seeded_item.id, ordinal=0, was_inserted=True),
    ])
    db_session.commit()

    response = client.post(
        f"/api/items/{seeded_item.id}/merge",
        json={"targetId": target.id},
    )

    assert response.status_code == 200
    assert response.json() == {
        "sourceId": seeded_item.id,
        "targetId": target.id,
        "movedLinks": 1,
        "removedDuplicates": 1,
    }
    db_session.refresh(seeded_item)
    assert seeded_item.is_invalid is True
    assert seeded_item.merged_into_id == target.id
    assert db_session.query(PublicationItem).filter_by(publication_id=first.id).count() == 1
    assert db_session.query(PublicationItem).filter_by(publication_id=second.id, item_id=target.id).count() == 1
    db_session.refresh(first)
    db_session.refresh(second)
    assert first.item_count == 2
    assert second.item_count == 1
    invalid = client.get("/api/items?state=invalid").json()
    assert any(item["id"] == seeded_item.id and item["mergedIntoId"] == target.id for item in invalid["items"])
    assert {revision.action for revision in db_session.query(ItemRevision).all()} == {"merged", "merge_target"}
    assert client.patch(f"/api/items/{seeded_item.id}", json={"isSaved": True}).status_code == 409
    assert client.patch(
        f"/api/items/{seeded_item.id}/content",
        json={"title": "不能修改", "summary": "审计记录", "kind": "news"},
    ).status_code == 409
    assert client.put(f"/api/items/{seeded_item.id}/validity", json={"invalid": True}).status_code == 409


def test_merge_candidates_prioritize_similar_titles(
    client: TestClient,
    db_session: Session,
    seeded_item,
    subscription,
) -> None:
    similar = IntelligenceItem(
        subscription_id=subscription.id,
        kind="news",
        title="Agent框架发布新版",
        summary="相似内容",
        url="https://example.com/agent-release-2",
        source="Example",
        keywords_json="[]",
        fingerprint=item_fingerprint("Agent框架发布新版", "https://example.com/agent-release-2"),
    )
    unrelated = IntelligenceItem(
        subscription_id=subscription.id,
        kind="news",
        title="完全无关的行业新闻",
        summary="无关内容",
        url="https://example.com/unrelated",
        source="Example",
        keywords_json="[]",
        fingerprint=item_fingerprint("完全无关的行业新闻", "https://example.com/unrelated"),
    )
    db_session.add_all([unrelated, similar])
    db_session.commit()

    response = client.get(f"/api/items/{seeded_item.id}/merge-candidates")

    assert response.status_code == 200
    assert response.json()[0]["id"] == similar.id


def test_item_detail_exposes_revision_history_and_merge_target(
    client: TestClient,
    db_session: Session,
    seeded_item,
    subscription,
) -> None:
    target = IntelligenceItem(
        subscription_id=subscription.id,
        kind="news",
        title="保留情报",
        summary="目标",
        url="https://example.com/target",
        source="Example",
        keywords_json="[]",
        fingerprint=item_fingerprint("保留情报", "https://example.com/target"),
    )
    db_session.add(target)
    db_session.flush()
    seeded_item.is_invalid = True
    seeded_item.merged_into_id = target.id
    db_session.add(
        ItemRevision(
            item_id=seeded_item.id,
            action="merged",
            before_json='{"title": "旧标题"}',
            after_json=f'{{"mergedIntoId": {target.id}}}',
        )
    )
    db_session.commit()

    response = client.get(f"/api/items/{seeded_item.id}")

    assert response.status_code == 200
    assert response.json()["mergedInto"] == {"id": target.id, "title": "保留情报"}
    assert response.json()["revisions"][0]["action"] == "merged"

