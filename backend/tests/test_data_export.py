import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    Briefing,
    HermesPreference,
    HermesPublication,
    IntelligenceItem,
    ItemTag,
    ItemTopic,
    PublicationItem,
    Subscription,
    TaskRun,
    Topic,
)
from app.ops.content_export import validate_export
from app.services.data_export import DataExportService, ExportFilters, clean_text, safe_url


def seed_export_graph(db: Session, subscription: Subscription, item: IntelligenceItem) -> Topic:
    item.url = "https://example.com/story?token=private-token&ref=weekly"
    item.summary = "公开摘要；api_key=should-not-leak；内部地址http://host.docker.internal:8642/run"
    topic = Topic(name="智能体", normalized_name="智能体", description="Agent进展", is_followed=True)
    task = TaskRun(
        subscription_id=subscription.id,
        trace_id="trace-public",
        origin="weixin-hermes",
        topic="智能体",
        request_summary="这是完整微信消息，不能导出",
        result_summary="已整理，Authorization: Bearer top-secret-token",
        raw_output="绝不能出现在导出中",
        error_message="也不能出现在导出中",
        status="completed",
        stage="published",
        finished_at=datetime.now(timezone.utc),
    )
    report = Briefing(
        subscription_id=subscription.id,
        title="智能体周报",
        kind="news",
        content="结论来自[1]，secret=hidden-value。",
        item_count=1,
        generation_task_id=None,
        citation_status="verified",
    )
    preference = HermesPreference(
        scope="topic",
        effect="boost",
        value="智能体",
        kind="news",
        note="长期关注，mcp_token=hidden-token",
    )
    db.add_all([topic, task, report, preference])
    db.flush()
    report.generation_task_id = task.id
    publication = HermesPublication(
        idempotency_key="export-test-publication",
        payload_hash="b" * 64,
        subscription_id=subscription.id,
        briefing_id=report.id,
        trace_id=task.trace_id,
        hermes_run_id="private-hermes-run",
        task_run_id=task.id,
        item_count=1,
        topic="智能体",
        request_summary="另一条完整微信消息",
    )
    db.add(publication)
    db.flush()
    db.add_all([
        ItemTag(item_id=item.id, name="Agent"),
        ItemTopic(item_id=item.id, topic_id=topic.id, source="keyword", confidence=0.96),
        PublicationItem(publication_id=publication.id, item_id=item.id, ordinal=1, was_inserted=True),
    ])
    db.commit()
    return topic


def test_json_export_preserves_graph_and_removes_sensitive_data(
    client: TestClient,
    db_session: Session,
    subscription: Subscription,
    seeded_item: IntelligenceItem,
    tmp_path: Path,
) -> None:
    topic = seed_export_graph(db_session, subscription, seeded_item)
    response = client.get("/api/export", params={"format": "json", "topicId": topic.id})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "attachment" in response.headers["content-disposition"]
    payload = response.json()
    assert payload["schemaVersion"] == 1
    assert payload["counts"]["items"] == 1
    assert payload["data"]["subscriptionRefs"] == [{
        "id": subscription.id,
        "name": subscription.name,
        "kind": subscription.kind,
    }]
    assert payload["data"]["items"][0]["fingerprint"] == seeded_item.fingerprint
    assert payload["data"]["reportSources"] == [{
        "reportId": payload["data"]["reports"][0]["id"],
        "publicationId": payload["data"]["publications"][0]["id"],
        "itemId": seeded_item.id,
        "ordinal": 1,
        "wasInserted": True,
        "title": seeded_item.title,
        "summary": clean_text(seeded_item.summary),
        "kind": seeded_item.kind,
        "publishedAt": None,
        "fingerprint": seeded_item.fingerprint,
        "source": seeded_item.source,
        "originalUrl": "https://example.com/story?ref=weekly",
    }]
    serialized = response.text
    for forbidden in (
        "should-not-leak", "top-secret-token", "hidden-value", "hidden-token",
        "host.docker.internal", "完整微信消息", "private-hermes-run", "绝不能出现在导出中",
    ):
        assert forbidden not in serialized
    assert "rawOutput" not in serialized
    assert "requestSummary" not in serialized
    export_path = tmp_path / "export.json"
    export_path.write_bytes(response.content)
    assert validate_export(export_path)["status"] == "ok"


def test_markdown_export_and_filters(
    client: TestClient,
    db_session: Session,
    subscription: Subscription,
    seeded_item: IntelligenceItem,
) -> None:
    topic = seed_export_graph(db_session, subscription, seeded_item)
    response = client.get("/api/export", params=[
        ("format", "markdown"), ("topicId", str(topic.id)), ("kind", "news"),
        ("include", "reports"), ("include", "sources"),
    ])

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "# 知流数据导出" in response.text
    assert "[打开原文](<https://example.com/story?ref=weekly>)" in response.text
    assert "## items" not in response.text
    assert "## reports" in response.text
    assert "hidden-value" not in response.text


def test_date_filter_keeps_report_evidence_even_when_source_item_is_older(
    client: TestClient,
    db_session: Session,
    subscription: Subscription,
    seeded_item: IntelligenceItem,
    tmp_path: Path,
) -> None:
    seed_export_graph(db_session, subscription, seeded_item)
    seeded_item.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    db_session.commit()
    today = datetime.now(timezone.utc).date().isoformat()

    response = client.get("/api/export", params={"fromDate": today})
    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"]["items"] == 0
    assert payload["counts"]["reports"] == 1
    assert payload["data"]["reportSources"][0]["itemId"] == seeded_item.id
    assert payload["data"]["reportSources"][0]["originalUrl"] == "https://example.com/story?ref=weekly"
    path = tmp_path / "filtered.json"
    path.write_bytes(response.content)
    assert validate_export(path)["status"] == "ok"


@pytest.mark.parametrize("params", [
    {"fromDate": "2026-08-24", "toDate": "2026-08-23"},
    {"topicId": "99999"},
    {"include": "unknown"},
])
def test_export_rejects_invalid_filters(client: TestClient, params: dict[str, str]) -> None:
    response = client.get("/api/export", params=params)
    assert response.status_code in {404, 422}


def test_export_handles_more_than_one_thousand_items(
    client: TestClient,
    db_session: Session,
    subscription: Subscription,
) -> None:
    db_session.add_all([
        IntelligenceItem(
            subscription_id=subscription.id,
            kind="news",
            title=f"情报{i}",
            summary="摘要",
            url=f"https://example.com/items/{i}",
            source="批量来源",
            fingerprint=f"{i:064x}",
        )
        for i in range(1005)
    ])
    db_session.commit()

    response = client.get("/api/export", params={"include": "items"})
    assert response.status_code == 200
    assert response.json()["counts"]["items"] == 1005


def test_failed_export_deletes_partial_file(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    partial = tmp_path / "partial.json"

    def fake_mkstemp(**_kwargs):
        return os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), str(partial)

    def fail_write(*_args, **_kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr("app.services.data_export.tempfile.mkstemp", fake_mkstemp)
    monkeypatch.setattr(DataExportService, "_write_json", fail_write)
    with pytest.raises(RuntimeError, match="write failed"):
        DataExportService(db_session, ExportFilters()).build("json")
    assert not partial.exists()


def test_validator_rejects_broken_references(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text(json.dumps({
        "schemaVersion": 1,
        "data": {"items": [{"id": 1}], "itemTopics": [{"itemId": 2, "topicId": 1}]},
        "counts": {"items": 1, "itemTopics": 1},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="导出范围外"):
        validate_export(path)


@pytest.mark.parametrize("url", [
    "http://127.1/admin",
    "http://127.0.0.1.nip.io/admin",
    "http://10-0-0-4.sslip.io/admin",
    "http://[::1]/admin",
    "http://hermes.internal/admin",
])
def test_safe_url_rejects_internal_address_variants(url: str) -> None:
    assert safe_url(url) is None


def test_validator_checks_relations_when_principal_collection_is_empty(tmp_path: Path) -> None:
    path = tmp_path / "broken-empty.json"
    path.write_text(json.dumps({
        "schemaVersion": 1,
        "data": {"reports": [], "reportSources": [{"reportId": 9}]},
        "counts": {"reports": 0, "reportSources": 1},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="不存在的报告"):
        validate_export(path)


def test_validator_rejects_extra_count_keys(tmp_path: Path) -> None:
    path = tmp_path / "extra-count.json"
    path.write_text(json.dumps({
        "schemaVersion": 1,
        "data": {"items": []},
        "counts": {"items": 0, "unexpected": 1},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="计数项目不一致"):
        validate_export(path)
