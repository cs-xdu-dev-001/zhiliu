from importlib import import_module

from fastapi.testclient import TestClient


def test_health_endpoint_reports_zhiliu_service() -> None:
    app_module = import_module("app.main")
    with TestClient(app_module.app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "zhiliu"}

