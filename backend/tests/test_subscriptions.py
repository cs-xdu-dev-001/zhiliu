from datetime import datetime

from fastapi.testclient import TestClient


def test_create_subscription_returns_normalized_payload(client: TestClient) -> None:
    payload = {
        "name": "Agent论文",
        "kind": "paper",
        "keywords": ["LLM Agent"],
        "schedule": "0 9 * * 1",
        "prompt": "检索过去7天的论文",
        "enabled": True,
    }

    response = client.post("/api/subscriptions", json=payload)

    assert response.status_code == 201
    assert response.json()["keywords"] == ["LLM Agent"]
    assert response.json()["kind"] == "paper"
    assert response.json()["nextRunAt"] is not None
    next_run_at = datetime.fromisoformat(response.json()["nextRunAt"])
    assert next_run_at.weekday() == 0
    assert (next_run_at.hour, next_run_at.minute) == (9, 0)


def test_create_subscription_rejects_invalid_cron(client: TestClient) -> None:
    response = client.post(
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


def test_update_and_delete_subscription(client: TestClient, subscription) -> None:
    update = client.put(
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
    deleted = client.delete(f"/api/subscriptions/{subscription.id}")

    assert update.status_code == 200
    assert update.json()["name"] == "AI热点精选"
    assert update.json()["enabled"] is False
    assert update.json()["nextRunAt"] is None
    assert deleted.status_code == 204


def test_subscription_list_exposes_next_run_for_enabled_records(client: TestClient, subscription) -> None:
    response = client.get("/api/subscriptions")

    assert response.status_code == 200
    assert response.json()[0]["id"] == subscription.id
    assert response.json()[0]["nextRunAt"] is not None

