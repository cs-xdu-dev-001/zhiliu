from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Briefing, HermesPublication, PublicationItem


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
        }
    ]


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
