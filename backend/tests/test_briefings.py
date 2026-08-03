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
