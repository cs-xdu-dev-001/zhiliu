from fastapi.testclient import TestClient

from app.models import User


def test_login_sets_http_only_cookie(client: TestClient, seeded_user: User) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "test-pass"},
    )

    assert response.status_code == 204
    assert "zhiliu_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_protected_endpoint_rejects_anonymous(client: TestClient) -> None:
    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_authenticated_user_can_read_profile(auth_client: TestClient) -> None:
    response = auth_client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {"id": 1, "username": "admin"}


def test_login_rejects_wrong_password(client: TestClient, seeded_user: User) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )

    assert response.status_code == 401

