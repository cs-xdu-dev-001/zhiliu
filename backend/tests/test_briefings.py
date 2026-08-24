import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Briefing, HermesPublication, IntelligenceItem, PublicationItem, TaskRun
from app.services.run_service import item_fingerprint


def test_briefing_detail_returns_exact_source_items(
    client: TestClient,
    db_session: Session,
    seeded_item,
    subscription,
) -> None:
    briefing = Briefing(
        subscription_id=subscription.id,
        title="Agent报告",
        kind="news",
        content="报告正文",
        item_count=1,
    )
    db_session.add(briefing)
    db_session.flush()
    publication = HermesPublication(
        idempotency_key="briefing-detail-trace",
        payload_hash="c" * 64,
        subscription_id=subscription.id,
        briefing_id=briefing.id,
        trace_id="trace-briefing-detail",
        item_count=0,
        skipped_count=1,
        topic="Agent更新",
        request_summary="生成Agent报告",
        origin="weixin-hermes",
    )
    db_session.add(publication)
    db_session.flush()
    db_session.add(
        PublicationItem(
            publication_id=publication.id,
            item_id=seeded_item.id,
            ordinal=0,
            was_inserted=False,
        )
    )
    db_session.commit()

    response = client.get(f"/api/briefings/{briefing.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["traceAvailable"] is True
    assert payload["publication"]["id"] == publication.id
    assert payload["sourceItems"] == [
        {
            "id": seeded_item.id,
            "title": seeded_item.title,
            "summary": seeded_item.summary,
            "source": seeded_item.source,
            "url": seeded_item.url,
            "ordinal": 0,
            "wasInserted": False,
            "isInvalid": False,
            "sourceUnavailable": False,
            "isCited": False,
            "evidenceStatus": "unreferenced",
            "evidenceMessage": "正文未引用该来源",
        }
    ]


def test_briefing_detail_returns_traceable_evidence_and_version_diff(
    client: TestClient,
    db_session: Session,
    seeded_item,
    subscription,
) -> None:
    extra = IntelligenceItem(
        subscription_id=subscription.id,
        kind="paper",
        title="新增论文来源",
        summary="补充证据",
        url="https://example.com/new-source",
        source="Example",
        keywords_json="[]",
        fingerprint=item_fingerprint("新增论文来源", "https://example.com/new-source"),
    )
    db_session.add(extra)
    previous = Briefing(
        subscription_id=subscription.id,
        title="Agent专题",
        kind="news",
        content="旧结论[1]",
        item_count=1,
        series_id="series-diff",
        version_number=1,
    )
    db_session.add(previous)
    db_session.flush()
    current = Briefing(
        subscription_id=subscription.id,
        title="Agent专题更新",
        kind="news",
        content="新结论[1]\n新增判断[1]",
        item_count=1,
        series_id="series-diff",
        version_number=2,
        previous_version_id=previous.id,
        citation_status="valid",
    )
    db_session.add(current)
    db_session.flush()
    for index, briefing in enumerate((previous, current), start=1):
        publication = HermesPublication(
            idempotency_key=f"briefing-version-{index}",
            payload_hash=f"{index}" * 64,
            subscription_id=subscription.id,
            briefing_id=briefing.id,
            item_count=1,
            skipped_count=0,
            topic=briefing.title,
            request_summary="完整展开" if index == 1 else "压缩背景",
            origin="web-report",
        )
        db_session.add(publication)
        db_session.flush()
        db_session.add(PublicationItem(
            publication_id=publication.id,
            item_id=seeded_item.id,
            ordinal=0,
            was_inserted=False,
        ))
        if index == 2:
            db_session.add(PublicationItem(
                publication_id=publication.id,
                item_id=extra.id,
                ordinal=1,
                was_inserted=False,
            ))
    db_session.commit()

    payload = client.get(f"/api/briefings/{current.id}").json()

    assert payload["sourceItems"][0]["isCited"] is True
    assert payload["sourceItems"][0]["evidenceStatus"] == "traceable"
    assert payload["versionDiff"]["previousVersionId"] == previous.id
    assert payload["versionDiff"]["previousVersionNumber"] == 1
    assert payload["versionDiff"]["titleChanged"] is True
    assert payload["versionDiff"]["instructionChanged"] is True
    assert payload["versionDiff"]["previousInstruction"] == "完整展开"
    assert payload["versionDiff"]["currentInstruction"] == "压缩背景"
    assert payload["versionDiff"]["addedSources"] == [{"id": extra.id, "title": "新增论文来源"}]
    assert payload["versionDiff"]["addedSegmentCount"] == 2
    assert payload["versionDiff"]["removedSegmentCount"] == 1
    assert len(payload["versionDiff"]["changes"]) == 3
    assert "content" not in payload["versions"][0]


def test_historical_briefing_does_not_guess_sources(
    client: TestClient,
    db_session: Session,
    subscription,
) -> None:
    briefing = Briefing(
        subscription_id=subscription.id,
        title="历史报告",
        kind="news",
        content="历史正文",
        item_count=3,
    )
    db_session.add(briefing)
    db_session.commit()

    response = client.get(f"/api/briefings/{briefing.id}")

    assert response.json()["traceAvailable"] is False
    assert response.json()["sourceItems"] == []
    assert response.json()["publication"] is None


def test_briefing_list_supports_search_filters_and_stable_pagination(
    client: TestClient,
    db_session: Session,
    subscription,
) -> None:
    created_at = datetime.now(timezone.utc) - timedelta(days=2)
    reports = [
        Briefing(subscription_id=subscription.id, title="Agent日报", kind="news", content="工具调用更新", item_count=2, created_at=created_at),
        Briefing(subscription_id=subscription.id, title="RAG周报", kind="paper", content="100%覆盖率测试", item_count=3, created_at=created_at),
        Briefing(subscription_id=subscription.id, title="旧招聘报告", kind="job", content="历史岗位", item_count=1, created_at=created_at - timedelta(days=60)),
    ]
    db_session.add_all(reports)
    db_session.commit()

    searched = client.get("/api/briefings?q=100%25")
    filtered = client.get("/api/briefings?kind=paper&days=7")
    first = client.get("/api/briefings?limit=1&offset=0")
    second = client.get("/api/briefings?limit=1&offset=1")

    assert [item["id"] for item in searched.json()["items"]] == [reports[1].id]
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["title"] == "RAG周报"
    assert first.json()["items"][0]["id"] == reports[1].id
    assert second.json()["items"][0]["id"] == reports[0].id


def test_briefing_list_only_shows_latest_report_version(
    client: TestClient,
    db_session: Session,
    subscription,
) -> None:
    versions = [
        Briefing(subscription_id=subscription.id, title="专题v1", kind="news", content="旧版", item_count=1, series_id="series-list", version_number=1),
        Briefing(subscription_id=subscription.id, title="专题v2", kind="news", content="新版", item_count=1, series_id="series-list", version_number=2),
    ]
    db_session.add_all(versions)
    db_session.commit()

    response = client.get("/api/briefings")

    assert response.status_code == 200
    assert [item["title"] for item in response.json()["items"]] == ["专题v2"]


def test_generate_briefing_queues_idempotent_report_task(
    client: TestClient,
    db_session: Session,
    seeded_item,
) -> None:
    payload = {
        "itemIds": [seeded_item.id],
        "instruction": "突出研究影响",
        "requestId": "report-request-123",
    }

    first = client.post("/api/briefings/generate", json=payload)
    second = client.post("/api/briefings/generate", json=payload)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]
    assert first.json()["origin"] == "web-report"
    task = db_session.get(TaskRun, first.json()["id"])
    assert task.report_item_ids_json == f"[{seeded_item.id}]"
    assert task.report_version_number == 1


def test_generate_briefing_rejects_request_id_reuse_with_different_payload(
    client: TestClient,
    seeded_item,
) -> None:
    request_id = "report-request-conflict"
    first = client.post(
        "/api/briefings/generate",
        json={"itemIds": [seeded_item.id], "instruction": "初版", "requestId": request_id},
    )
    conflict = client.post(
        "/api/briefings/generate",
        json={"itemIds": [seeded_item.id], "instruction": "另一要求", "requestId": request_id},
    )

    assert first.status_code == 202
    assert conflict.status_code == 409


def test_generate_briefing_normalizes_duplicate_source_ids(
    client: TestClient,
    seeded_item,
) -> None:
    request_id = "report-request-normalized"
    first = client.post(
        "/api/briefings/generate",
        json={
            "itemIds": [seeded_item.id, seeded_item.id],
            "instruction": "去重来源",
            "requestId": request_id,
        },
    )
    repeated = client.post(
        "/api/briefings/generate",
        json={
            "itemIds": [seeded_item.id],
            "instruction": "去重来源",
            "requestId": request_id,
        },
    )

    assert first.status_code == 202
    assert repeated.status_code == 202
    assert repeated.json()["id"] == first.json()["id"]


def test_regenerate_briefing_reuses_sources_and_increments_version(
    client: TestClient,
    db_session: Session,
    seeded_item,
    subscription,
) -> None:
    briefing = Briefing(
        subscription_id=subscription.id,
        title="专题报告",
        kind="news",
        content="正文[1]",
        item_count=1,
        series_id="series-1",
        version_number=1,
    )
    db_session.add(briefing)
    db_session.flush()
    publication = HermesPublication(
        idempotency_key="report-v1",
        payload_hash="d" * 64,
        subscription_id=subscription.id,
        briefing_id=briefing.id,
        item_count=0,
        skipped_count=1,
        topic=briefing.title,
        request_summary="初版",
        origin="web-report",
    )
    db_session.add(publication)
    db_session.flush()
    db_session.add(PublicationItem(publication_id=publication.id, item_id=seeded_item.id, ordinal=0, was_inserted=False))
    db_session.commit()

    response = client.post(
        f"/api/briefings/{briefing.id}/regenerate",
        json={"instruction": "更精炼", "requestId": "report-request-v2"},
    )

    assert response.status_code == 202
    task = db_session.get(TaskRun, response.json()["id"])
    assert task.report_series_id == "series-1"
    assert task.report_version_number == 2


def test_regenerate_briefing_can_add_new_sources(
    client: TestClient,
    db_session: Session,
    seeded_item,
    subscription,
) -> None:
    extra = IntelligenceItem(
        subscription_id=subscription.id,
        kind="paper",
        title="补充论文",
        summary="补充证据",
        url="https://example.com/extra-paper",
        source="Example",
        keywords_json="[]",
        fingerprint=item_fingerprint("补充论文", "https://example.com/extra-paper"),
    )
    briefing = Briefing(subscription_id=subscription.id, title="专题", kind="news", content="正文[1]", item_count=1, series_id="series-extra", version_number=1)
    db_session.add_all([extra, briefing])
    db_session.flush()
    publication = HermesPublication(
        idempotency_key="report-extra-v1", payload_hash="f" * 64, subscription_id=subscription.id,
        briefing_id=briefing.id, item_count=1, skipped_count=0, topic=briefing.title,
        request_summary="初版", origin="web-report",
    )
    db_session.add(publication)
    db_session.flush()
    db_session.add(PublicationItem(publication_id=publication.id, item_id=seeded_item.id, ordinal=0, was_inserted=False))
    db_session.commit()

    response = client.post(
        f"/api/briefings/{briefing.id}/regenerate",
        json={"instruction": "补充论文证据", "requestId": "report-extra-v2", "itemIds": [extra.id]},
    )

    assert response.status_code == 202
    task = db_session.get(TaskRun, response.json()["id"])
    assert json.loads(task.report_item_ids_json) == [seeded_item.id, extra.id]


def test_regenerate_briefing_rejects_competing_active_version(
    client: TestClient,
    db_session: Session,
    seeded_item,
    subscription,
) -> None:
    briefing = Briefing(subscription_id=subscription.id, title="专题", kind="news", content="正文[1]", item_count=1, series_id="series-active", version_number=1)
    db_session.add(briefing)
    db_session.flush()
    publication = HermesPublication(
        idempotency_key="report-active-v1", payload_hash="a1" * 32, subscription_id=subscription.id,
        briefing_id=briefing.id, item_count=1, skipped_count=0, topic=briefing.title,
        request_summary="初版", origin="web-report",
    )
    db_session.add(publication)
    db_session.flush()
    db_session.add(PublicationItem(publication_id=publication.id, item_id=seeded_item.id, ordinal=0, was_inserted=False))
    db_session.commit()

    first_payload = {"instruction": "第一项调整", "requestId": "report-active-first"}
    first = client.post(f"/api/briefings/{briefing.id}/regenerate", json=first_payload)
    duplicate = client.post(f"/api/briefings/{briefing.id}/regenerate", json=first_payload)
    competing = client.post(
        f"/api/briefings/{briefing.id}/regenerate",
        json={"instruction": "不同调整", "requestId": "report-active-second"},
    )

    assert first.status_code == 202
    assert duplicate.status_code == 202
    assert duplicate.json()["id"] == first.json()["id"]
    assert competing.status_code == 409
    assert db_session.query(TaskRun).filter(TaskRun.report_series_id == "series-active").count() == 1


def test_regenerate_briefing_failure_does_not_partially_assign_series(
    client: TestClient,
    db_session: Session,
    seeded_item,
    subscription,
) -> None:
    briefing = Briefing(
        subscription_id=subscription.id,
        title="旧报告",
        kind="news",
        content="正文",
        item_count=1,
    )
    db_session.add(briefing)
    db_session.flush()
    publication = HermesPublication(
        idempotency_key="legacy-report",
        payload_hash="e" * 64,
        subscription_id=subscription.id,
        briefing_id=briefing.id,
        item_count=1,
        skipped_count=0,
        topic=briefing.title,
        request_summary="旧版",
        origin="web-report",
    )
    db_session.add(publication)
    db_session.flush()
    db_session.add(PublicationItem(publication_id=publication.id, item_id=seeded_item.id, ordinal=0, was_inserted=True))
    seeded_item.is_invalid = True
    db_session.commit()

    response = client.post(
        f"/api/briefings/{briefing.id}/regenerate",
        json={"instruction": "重试", "requestId": "legacy-report-failure"},
    )

    assert response.status_code == 409
    db_session.expire_all()
    unchanged = db_session.get(Briefing, briefing.id)
    assert unchanged is not None
    assert unchanged.series_id is None
    assert unchanged.version_number == 1
