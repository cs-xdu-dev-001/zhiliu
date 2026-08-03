from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.models import TaskRun


def test_manual_run_queues_task(client: TestClient, subscription) -> None:
    response = client.post(f"/api/subscriptions/{subscription.id}/run")
    listed = client.get("/api/runs?limit=1")

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert listed.status_code == 200
    assert listed.json()["items"][0]["subscriptionId"] == subscription.id


def test_duplicate_active_run_is_rejected(client: TestClient, running_task) -> None:
    response = client.post(f"/api/subscriptions/{running_task.subscription_id}/run")

    assert response.status_code == 409


def test_run_list_is_public(client: TestClient) -> None:
    response = client.get("/api/runs")

    assert response.status_code == 200


def test_run_detail_exposes_feedback_and_linked_result(client: TestClient, db_session, subscription) -> None:
    from app.models import Briefing, HermesPublication, TaskRun

    task = TaskRun(
        subscription_id=subscription.id,
        trace_id="trace-run-detail",
        origin="weixin-hermes",
        topic="Agent更新",
        request_summary="整理今天的Agent更新",
        status="success",
        stage="completed",
        result_summary="新增2条情报，生成1份报告",
    )
    db_session.add(task)
    db_session.flush()
    briefing = Briefing(
        subscription_id=subscription.id,
        title="Agent更新简报",
        kind="news",
        content="正文",
        item_count=2,
    )
    db_session.add(briefing)
    db_session.flush()
    publication = HermesPublication(
        idempotency_key="run-detail-key",
        payload_hash="b" * 64,
        subscription_id=subscription.id,
        briefing_id=briefing.id,
        trace_id=task.trace_id,
        task_run_id=task.id,
        item_count=2,
        skipped_count=0,
        topic=task.topic,
        request_summary=task.request_summary,
        origin=task.origin,
    )
    db_session.add(publication)
    db_session.commit()

    response = client.get(f"/api/runs/{task.id}")

    assert response.status_code == 200
    assert response.json() | {
        "topic": "Agent更新",
        "stage": "completed",
        "resultSummary": "新增2条情报，生成1份报告",
        "publicationId": publication.id,
        "briefingId": briefing.id,
    } == response.json()


def test_run_list_has_stable_pagination_and_server_side_status_filter(
    client: TestClient,
    db_session,
    subscription,
) -> None:
    started_at = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    records = [
        TaskRun(subscription_id=subscription.id, status="failed", stage="failed", started_at=started_at),
        TaskRun(subscription_id=subscription.id, status="success", stage="completed", started_at=started_at),
        TaskRun(subscription_id=subscription.id, status="failed", stage="failed", started_at=started_at),
    ]
    db_session.add_all(records)
    db_session.commit()

    first = client.get("/api/runs?limit=2&offset=0")
    second = client.get("/api/runs?limit=2&offset=2")
    failed = client.get("/api/runs?status=failed&limit=10")

    assert [item["id"] for item in first.json()["items"]] == [records[2].id, records[1].id]
    assert [item["id"] for item in second.json()["items"]] == [records[0].id]
    assert failed.json()["total"] == 2
    assert [item["id"] for item in failed.json()["items"]] == [records[2].id, records[0].id]


def test_run_list_query_count_does_not_grow_with_records(
    client: TestClient,
    db_session,
    subscription,
) -> None:
    db_session.add_all([TaskRun(subscription_id=subscription.id) for _ in range(8)])
    db_session.commit()
    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        response = client.get("/api/runs?limit=8")
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    assert response.status_code == 200
    assert len(response.json()["items"]) == 8
    assert len(statements) == 4

