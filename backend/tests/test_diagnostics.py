from datetime import datetime, timedelta, timezone
from importlib import import_module

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.db import get_db
from app.models import HermesIntegration, HermesPublication, TaskRun


def test_diagnostics_returns_non_sensitive_runtime_summary(client: TestClient, db_session, subscription) -> None:
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            TaskRun(subscription_id=subscription.id, status="queued", started_at=now - timedelta(seconds=30)),
            TaskRun(subscription_id=subscription.id, status="running", started_at=now - timedelta(seconds=20)),
            TaskRun(subscription_id=subscription.id, status="success", finished_at=now - timedelta(minutes=2)),
        ]
    )
    db_session.add(
        HermesIntegration(
            id=1,
            base_url="http://private-hermes:8642",
            encrypted_api_key="encrypted-secret",
            api_key_hint="••••abcd",
            last_status="connected",
            last_message="internal details",
            last_checked_at=now,
        )
    )
    db_session.add(
        HermesPublication(
            idempotency_key="diagnostics-publication",
            payload_hash="d" * 64,
            subscription_id=subscription.id,
            item_count=2,
            topic="diagnostics",
            request_summary="safe summary",
        )
    )
    db_session.commit()

    response = client.get("/api/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"]["status"] == "ok"
    assert payload["queue"]["queued"] == 1
    assert payload["queue"]["running"] == 1
    assert payload["queue"]["oldestActiveSeconds"] >= 29
    assert payload["hermes"] == {
        "configured": True,
        "status": "connected",
        "checkedAt": payload["hermes"]["checkedAt"],
    }
    assert payload["mcp"]["status"] == "verified"
    assert payload["mcp"]["lastWriteAt"] is not None
    assert payload["scheduler"]["enabled"] is False
    assert payload["scheduler"]["running"] is False
    assert "private-hermes" not in response.text
    assert "encrypted-secret" not in response.text
    assert "abcd" not in response.text
    assert "internal details" not in response.text


def test_diagnostics_reports_database_failure_without_leaking_details() -> None:
    app_module = import_module("app.main")
    test_app = app_module.create_app(
        start_background_scheduler=False,
        settings=Settings(scheduler_enabled=False, demo_mode=False, _env_file=None),
    )

    class BrokenDatabase:
        def execute(self, _statement):
            raise OperationalError("SELECT 1", {}, RuntimeError("/secret/data/zhiliu.db"))

    def broken_database():
        yield BrokenDatabase()

    test_app.dependency_overrides[get_db] = broken_database
    try:
        with TestClient(test_app) as client:
            response = client.get("/api/diagnostics")
    finally:
        test_app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["database"] == {
        "status": "unavailable",
        "latencyMs": None,
        "migrationVersion": None,
    }
    assert response.json()["mcp"] == {
        "status": "unknown",
        "lastWriteAt": None,
        "lastTaskStatus": None,
        "lastTaskAt": None,
    }
    assert "secret" not in response.text
