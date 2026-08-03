from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Briefing, HermesPublication, PublicationItem, TaskRun


def test_trace_endpoint_returns_full_chain_without_raw_output(
    client: TestClient,
    db_session: Session,
    seeded_item,
    subscription,
) -> None:
    task = TaskRun(
        subscription_id=subscription.id,
        hermes_run_id="hermes-trace-7",
        status="success",
        raw_output="不得返回的原始结果",
    )
    briefing = Briefing(
        subscription_id=subscription.id,
        title="完整链路报告",
        kind="news",
        content="报告正文",
        item_count=1,
    )
    db_session.add_all([task, briefing])
    db_session.flush()
    publication = HermesPublication(
        idempotency_key="full-trace",
        payload_hash="d" * 64,
        subscription_id=subscription.id,
        briefing_id=briefing.id,
        trace_id="trace-full-chain",
        hermes_run_id=task.hermes_run_id,
        task_run_id=task.id,
        item_count=1,
        skipped_count=0,
        topic="完整链路",
        request_summary="整理完整链路并写入知流",
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

    response = client.get(f"/api/publications/{publication.id}/trace")

    assert response.status_code == 200
    payload = response.json()
    assert payload["traceId"] == "trace-full-chain"
    assert payload["requestSummary"] == "整理完整链路并写入知流"
    assert payload["hermesRunId"] == "hermes-trace-7"
    assert payload["subscription"]["name"] == subscription.name
    assert payload["taskRun"]["id"] == task.id
    assert payload["items"][0]["url"] == seeded_item.url
    assert payload["briefing"]["id"] == briefing.id
    assert "rawOutput" not in response.text
    assert "不得返回的原始结果" not in response.text


def test_missing_trace_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/publications/999/trace")

    assert response.status_code == 404
    assert response.json()["detail"] == "追踪记录不存在"
