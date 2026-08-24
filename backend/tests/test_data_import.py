import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Briefing,
    HermesPreference,
    HermesPublication,
    ImportBatch,
    IntelligenceItem,
    ItemTag,
    ItemTopic,
    PublicationItem,
    Subscription,
    Topic,
)
from app.services.data_import import ContentImportService
from app.services.data_import import MAX_IMPORT_BYTES


def import_payload(*, report_version: int = 1, item_count: int = 1) -> dict:
    items = [
        {
            "id": index + 10,
            "subscriptionId": 1,
            "kind": "news",
            "title": f"迁移情报{index}",
            "summary": "用于验证安全内容迁移。",
            "originalUrl": f"https://example.com/migration/{index}",
            "source": "迁移测试",
            "publishedAt": "2026-08-24T08:00:00+00:00",
            "keywords": ["Agent"],
            "reason": "值得关注",
            "importance": 0.8,
            "isRead": False,
            "isSaved": index == 0,
            "isIgnored": False,
            "isInvalid": False,
            "sourceUnavailable": False,
            "latestChangeType": None,
            "mergedIntoId": None,
            "createdAt": "2026-08-24T09:00:00+00:00",
        }
        for index in range(item_count)
    ]
    data = {
        "subscriptionRefs": [{"id": 1, "name": "迁移订阅", "kind": "news"}],
        "items": items,
        "tags": [{"itemId": item["id"], "name": "迁移", "createdAt": "2026-08-24T09:01:00+00:00"} for item in items],
        "topics": [{
            "id": 5,
            "name": "智能体迁移",
            "description": "迁移主题",
            "aliases": ["Agent迁移"],
            "isFollowed": True,
            "isPinned": False,
            "isMuted": False,
            "mergedIntoId": None,
            "createdAt": "2026-08-24T09:00:00+00:00",
            "updatedAt": "2026-08-24T09:00:00+00:00",
        }],
        "itemTopics": [{"itemId": item["id"], "topicId": 5, "source": "migration", "confidence": 0.9} for item in items],
        "preferences": [{
            "id": 7,
            "scope": "topic",
            "effect": "prefer",
            "value": "智能体迁移",
            "kind": "news",
            "note": "迁移偏好",
            "active": True,
            "createdAt": "2026-08-24T09:00:00+00:00",
            "updatedAt": "2026-08-24T09:00:00+00:00",
        }],
        "reports": [{
            "id": 8,
            "subscriptionId": 1,
            "title": "迁移报告",
            "kind": "news",
            "content": "迁移报告正文[1]。",
            "itemCount": 1,
            "periodStart": "2026-08-23T00:00:00+00:00",
            "periodEnd": "2026-08-24T00:00:00+00:00",
            "seriesId": "11111111-1111-1111-1111-111111111111",
            "versionNumber": report_version,
            "previousVersionId": None,
            "generationTaskId": None,
            "citationStatus": "verified",
            "citationWarnings": [],
            "createdAt": "2026-08-24T09:00:00+00:00",
        }],
        "reportSources": [{
            "reportId": 8,
            "publicationId": 9,
            "itemId": 10,
            "ordinal": 1,
            "wasInserted": True,
            "title": "迁移情报0",
            "summary": "用于验证安全内容迁移。",
            "kind": "news",
            "publishedAt": "2026-08-24T08:00:00+00:00",
            "source": "迁移测试",
            "originalUrl": "https://example.com/migration/0",
        }],
        "tasks": [{"id": 99}],
        "publications": [{"id": 9}],
    }
    return {
        "schemaVersion": 1,
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "filters": {},
        "data": data,
        "counts": {name: len(records) for name, records in data.items()},
    }


def preview(client: TestClient, payload: dict) -> tuple[bytes, dict]:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    response = client.post("/api/import/preview", content=raw, headers={"Content-Type": "application/json"})
    assert response.status_code == 200, response.text
    return raw, response.json()


def confirm(client: TestClient, raw: bytes, token: str, strategy: str = "keep"):
    return client.post(
        f"/api/import/confirm?reportConflict={strategy}",
        content=raw,
        headers={"Content-Type": "application/json", "X-Import-Preview-Token": token},
    )


def undo(client: TestClient, batch_id: int):
    return client.post(
        f"/api/import/batches/{batch_id}/undo",
        headers={"X-Zhiliu-Action": "undo-import"},
    )


def test_preview_confirm_idempotency_and_safe_undo(client: TestClient, db_session: Session) -> None:
    raw, result = preview(client, import_payload())
    assert result["summary"]["items"]["create"] == 1
    assert result["unsupported"] == {"publications": 1, "tasks": 1}
    assert result["expiresAt"]

    response = confirm(client, raw, result["previewToken"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["idempotent"] is False
    batch_id = body["batch"]["id"]
    assert db_session.scalar(select(func.count()).select_from(IntelligenceItem)) == 1
    assert db_session.scalar(select(func.count()).select_from(Briefing)) == 1
    assert db_session.scalar(select(func.count()).select_from(HermesPublication)) == 1
    assert db_session.scalar(select(func.count()).select_from(PublicationItem)) == 1
    assert db_session.scalar(select(func.count()).select_from(Topic)) == 1
    assert db_session.scalar(select(func.count()).select_from(HermesPreference)) == 1

    repeated = confirm(client, raw, result["previewToken"])
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    assert repeated.json()["batch"]["id"] == batch_id

    listed = client.get("/api/import/batches")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == batch_id

    undone = undo(client, batch_id)
    assert undone.status_code == 200, undone.text
    assert undone.json()["batch"]["status"] == "undone"
    for model in (IntelligenceItem, Briefing, HermesPublication, PublicationItem, Topic, HermesPreference, Subscription):
        assert db_session.scalar(select(func.count()).select_from(model)) == 0


def test_undo_refuses_content_changed_after_import(client: TestClient, db_session: Session) -> None:
    raw, result = preview(client, import_payload())
    batch_id = confirm(client, raw, result["previewToken"]).json()["batch"]["id"]
    item = db_session.scalar(select(IntelligenceItem))
    item.title = "导入后人工修改"
    db_session.commit()

    response = undo(client, batch_id)
    assert response.status_code == 409
    assert "撤销未执行" in response.json()["detail"]
    assert db_session.get(IntelligenceItem, item.id) is not None
    assert db_session.get(ImportBatch, batch_id).status == "committed"


def test_undo_requires_same_origin_action_header(client: TestClient) -> None:
    raw, result = preview(client, import_payload())
    batch_id = confirm(client, raw, result["previewToken"]).json()["batch"]["id"]

    response = client.post(f"/api/import/batches/{batch_id}/undo")

    assert response.status_code == 422


def test_report_conflict_can_create_new_version(client: TestClient, db_session: Session) -> None:
    payload = import_payload()
    raw, result = preview(client, payload)
    first = confirm(client, raw, result["previewToken"])
    assert first.status_code == 200
    first_batch_id = first.json()["batch"]["id"]

    payload["data"]["reports"][0]["content"] = "冲突后的新正文"
    raw2, result2 = preview(client, payload)
    assert result2["summary"]["reports"]["conflict"] == 1
    second = confirm(client, raw2, result2["previewToken"], "new_version")
    assert second.status_code == 200, second.text
    versions = list(db_session.scalars(select(Briefing).order_by(Briefing.version_number)))
    assert [record.version_number for record in versions] == [1, 2]
    assert versions[1].previous_version_id == versions[0].id
    assert second.json()["batch"]["id"] != first_batch_id


def test_keep_report_conflict_does_not_attach_new_sources(client: TestClient, db_session: Session) -> None:
    payload = import_payload()
    raw, result = preview(client, payload)
    assert confirm(client, raw, result["previewToken"]).status_code == 200
    publication_count = db_session.scalar(select(func.count()).select_from(HermesPublication))
    source_count = db_session.scalar(select(func.count()).select_from(PublicationItem))

    payload["data"]["reports"][0]["content"] = "应被保留策略跳过的冲突正文"
    payload["data"]["reportSources"][0]["title"] = "不应追加到旧报告的来源"
    raw2, result2 = preview(client, payload)
    response = confirm(client, raw2, result2["previewToken"], "keep")

    assert response.status_code == 200, response.text
    assert db_session.scalar(select(func.count()).select_from(Briefing)) == 1
    assert db_session.scalar(select(func.count()).select_from(HermesPublication)) == publication_count
    assert db_session.scalar(select(func.count()).select_from(PublicationItem)) == source_count


def test_preview_token_is_bound_to_exact_file(client: TestClient) -> None:
    raw, result = preview(client, import_payload())
    changed = raw.replace(b"migration/0", b"migration/x", 1)
    response = confirm(client, changed, result["previewToken"])
    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "文件已变化，请重新预览"


@pytest.mark.parametrize("raw, expected", [
    (b'{"schemaVersion":1,"schemaVersion":1,"data":{},"counts":{}}', "重复字段"),
    (b'{"schemaVersion":1,"data":{"unknown":[]},"counts":{"unknown":0}}', "未知数据集"),
    (b'{"schemaVersion":1,"data":{"items":[]},"counts":{"items":1}}', "计数不一致"),
    (b'{"schemaVersion":1,"data":{},"counts":{},"secret":"x"}', "未知顶层字段"),
])
def test_strict_validation_rejects_malformed_files(client: TestClient, raw: bytes, expected: str) -> None:
    response = client.post("/api/import/preview", content=raw, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert expected in response.json()["detail"]["message"]


def test_import_transport_rejects_compression_and_oversized_body(client: TestClient) -> None:
    compressed = client.post(
        "/api/import/preview",
        content=b"{}",
        headers={"Content-Type": "application/json", "Content-Encoding": "gzip"},
    )
    assert compressed.status_code == 415

    oversized = client.post(
        "/api/import/preview",
        content=b"{" + b" " * MAX_IMPORT_BYTES + b"}",
        headers={"Content-Type": "application/json"},
    )
    assert oversized.status_code == 413


def test_confirm_is_atomic_when_write_fails(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    raw, result = preview(client, import_payload())

    def fail_preferences(*_args, **_kwargs):
        raise RuntimeError("forced atomic failure")

    monkeypatch.setattr(ContentImportService, "_commit_preferences", fail_preferences)
    with pytest.raises(RuntimeError, match="forced atomic failure"):
        confirm(client, raw, result["previewToken"])
    assert db_session.scalar(select(func.count()).select_from(IntelligenceItem)) == 0
    assert db_session.scalar(select(func.count()).select_from(ImportBatch)) == 0


def test_import_handles_more_than_one_thousand_items(client: TestClient, db_session: Session) -> None:
    payload = import_payload(item_count=1005)
    raw, result = preview(client, payload)
    assert result["summary"]["items"]["create"] == 1005
    response = confirm(client, raw, result["previewToken"])
    assert response.status_code == 200, response.text
    assert db_session.scalar(select(func.count()).select_from(IntelligenceItem)) == 1005
    assert db_session.scalar(select(func.count()).select_from(ItemTag)) == 1005
    assert db_session.scalar(select(func.count()).select_from(ItemTopic)) == 1005
