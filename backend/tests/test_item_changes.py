from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.mcp_server.schemas import PublishPayload
from app.mcp_server.service import PublicationConflict, PublicationService
from app.models import HermesPublication, IntelligenceItem, ItemChange


def payload(**changes) -> PublishPayload:
    data = {
        "idempotencyKey": "change-first-20260824",
        "traceId": "change-trace-20260824",
        "topic": "Agent",
        "kind": "news",
        "requestSummary": "整理Agent变化",
        "items": [{
            "title": "Agent框架更新", "summary": "首次发布。", "url": "https://example.com/change-agent",
            "source": "Example", "keywords": ["Agent"], "reason": "持续跟踪", "importance": 0.8,
        }],
    }
    data.update(deepcopy(changes))
    return PublishPayload.model_validate(data)


def test_publish_records_idempotent_first_appearance(db_session: Session) -> None:
    service = PublicationService(db_session)
    first = service.publish(payload())
    repeated = service.publish(payload())
    change = db_session.scalar(select(ItemChange))

    assert repeated.duplicate is True
    assert change.change_type == "first_appearance"
    assert change.publication_id == first.receipt_id
    assert db_session.scalar(select(func.count()).select_from(ItemChange)) == 1


def test_explicit_change_requires_related_item_and_sources() -> None:
    with pytest.raises(ValueError, match="relatedItemId"):
        payload(items=[{
            "title": "更新", "summary": "内容", "url": "https://example.com/update", "source": "Example",
            "importance": 0.8, "change": {"changeType": "important_update", "changeBasis": "官方发布新版本", "sourceUrls": ["https://example.com/update"]},
        }])


def test_publish_explicit_update_keeps_snapshot_and_exact_link(db_session: Session) -> None:
    service = PublicationService(db_session)
    service.publish(payload())
    item = db_session.scalar(select(IntelligenceItem))
    update = payload(
        idempotencyKey="change-update-20260824", traceId="change-update-trace-20260824",
        items=[{
            "title": "Agent框架更新", "summary": "新增长期记忆能力。", "url": "https://example.com/change-agent",
            "source": "Example", "keywords": ["Agent"], "reason": "影响工作流", "importance": 0.9,
            "change": {"changeType": "important_update", "relatedItemId": item.id, "changeBasis": "官方更新日志新增长期记忆", "sourceUrls": ["https://example.com/change-agent"]},
        }],
    )
    receipt = service.publish(update)
    events = list(db_session.scalars(select(ItemChange).order_by(ItemChange.id)).all())

    db_session.refresh(item)
    assert item.summary == "新增长期记忆能力。"
    assert events[-1].related_item_id == item.id
    assert events[-1].before_json != events[-1].after_json
    assert events[-1].publication_id == receipt.receipt_id


def test_invalid_change_association_rolls_back_publication(db_session: Session) -> None:
    invalid = payload(items=[{
        "title": "更新", "summary": "内容", "url": "https://example.com/update", "source": "Example", "importance": 0.8,
        "change": {"changeType": "ongoing", "relatedItemId": 9999, "changeBasis": "持续推进", "sourceUrls": ["https://example.com/update"]},
    }])
    with pytest.raises(PublicationConflict, match="zhiliu_search"):
        PublicationService(db_session).publish(invalid)
    assert db_session.scalar(select(func.count()).select_from(HermesPublication)) == 0
    assert db_session.scalar(select(func.count()).select_from(ItemChange)) == 0


def test_user_can_relink_and_unlink_change(client: TestClient, db_session: Session, seeded_item) -> None:
    PublicationService(db_session).publish(payload())
    item = db_session.scalar(select(IntelligenceItem).where(IntelligenceItem.id != seeded_item.id))
    change = db_session.scalar(select(ItemChange).where(ItemChange.item_id == item.id))

    relinked = client.patch(f"/api/items/{item.id}/changes/{change.id}", json={"relatedItemId": seeded_item.id, "changeType": "ongoing", "basis": "用户确认同属一个跟踪链"})
    unlinked = client.patch(f"/api/items/{item.id}/changes/{change.id}", json={"unlink": True})

    assert relinked.status_code == 200
    assert relinked.json()["relatedItemId"] == seeded_item.id
    assert relinked.json()["status"] == "corrected"
    assert unlinked.json()["relatedItemId"] is None
    assert unlinked.json()["status"] == "unlinked"


def test_source_unavailable_creates_traceable_invalid_change(client: TestClient, db_session: Session, seeded_item) -> None:
    response = client.put(f"/api/items/{seeded_item.id}/source-availability", json={"unavailable": True})
    event = db_session.scalar(select(ItemChange).where(ItemChange.item_id == seeded_item.id))
    assert response.status_code == 200
    assert event.change_type == "information_invalid"
    assert event.before_json != event.after_json


def test_changes_only_report_rejects_unchanged_items(client: TestClient, seeded_item) -> None:
    response = client.post("/api/briefings/generate", json={"itemIds": [seeded_item.id], "instruction": "", "requestId": "changes-only-report", "changesOnly": True})
    assert response.status_code == 422
    seeded_item.latest_change_type = "important_update"
    response = client.post("/api/briefings/generate", json={"itemIds": [seeded_item.id], "instruction": "", "requestId": "changes-only-report-2", "changesOnly": True})
    assert response.status_code == 202
    assert response.json()["requestSummary"].startswith("仅总结相较历史记录的新变化")
