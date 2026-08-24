from importlib import import_module

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db import get_db
from app.core.config import Settings


def test_health_endpoint_reports_zhiliu_service(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "zhiliu"}


def test_health_endpoint_reports_database_failure_without_leaking_details() -> None:
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
            response = client.get("/api/health")
    finally:
        test_app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert response.json() == {"detail": "数据库暂时不可用"}
    assert "secret" not in response.text

