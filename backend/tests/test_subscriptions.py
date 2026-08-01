from fastapi.testclient import TestClient


def test_create_subscription_returns_normalized_payload(auth_client: TestClient) -> None:
    payload = {
        "name": "Agent论文",
        "kind": "paper",
        "keywords": ["LLM Agent"],
        "schedule": "0 9 * * 1",
        "prompt": "检索过去7天的论文",
        "enabled": True,
    }

    response = auth_client.post("/api/subscriptions", json=payload)

    assert response.status_code == 201
    assert response.json()["keywords"] == ["LLM Agent"]
    assert response.json()["kind"] == "paper"


def test_create_subscription_rejects_invalid_cron(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/subscriptions",
        json={
            "name": "错误任务",
            "kind": "news",
            "keywords": [],
            "schedule": "every sometime",
            "prompt": "任务",
            "enabled": True,
        },
    )

    assert response.status_code == 422


def test_update_and_delete_subscription(auth_client: TestClient, subscription) -> None:
    update = auth_client.put(
        f"/api/subscriptions/{subscription.id}",
        json={
            "name": "AI热点精选",
            "kind": "news",
            "keywords": ["AI"],
            "schedule": "30 8 * * *",
            "prompt": "只保留五条",
            "enabled": False,
        },
    )
    deleted = auth_client.delete(f"/api/subscriptions/{subscription.id}")

    assert update.status_code == 200
    assert update.json()["name"] == "AI热点精选"
    assert update.json()["enabled"] is False
    assert deleted.status_code == 204

