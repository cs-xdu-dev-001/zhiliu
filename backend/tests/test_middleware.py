import logging

from fastapi.testclient import TestClient


def test_request_id_is_returned_and_safe_metadata_is_logged(client: TestClient, caplog) -> None:
    caplog.set_level(logging.INFO, logger="zhiliu.request")

    response = client.get(
        "/api/health?api_key=must-not-be-logged",
        headers={"Authorization": "Bearer must-not-be-logged", "X-Request-ID": "release-check-123"},
    )

    own_logs = "\n".join(record.getMessage() for record in caplog.records if record.name == "zhiliu.request")
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "release-check-123"
    assert "method=GET" in own_logs
    assert "path=/api/health" in own_logs
    assert "status=200" in own_logs
    assert "api_key" not in own_logs
    assert "must-not-be-logged" not in own_logs
    assert "Authorization" not in own_logs


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "bad value"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] != "bad value"
    assert len(response.headers["x-request-id"]) == 32
