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


def test_preview_schedule_uses_project_cron_semantics(client: TestClient) -> None:
    response = client.post("/api/subscriptions/preview-schedule", json={"schedule": "0 9 * * 1"})

    assert response.status_code == 200
    assert response.json()["valid"] is True
    runs = response.json()["nextRuns"]
    assert len(runs) == 3
    assert all(datetime.fromisoformat(value).weekday() == 0 for value in runs)


def test_preview_schedule_returns_readable_error(client: TestClient) -> None:
    response = client.post("/api/subscriptions/preview-schedule", json={"schedule": "not a cron"})

    assert response.status_code == 200
    assert response.json() == {"valid": False, "nextRuns": [], "message": "请使用五段Cron表达式，星期建议使用mon至sun"}


def test_draft_subscription_requires_hermes_connection(client: TestClient) -> None:
    response = client.post("/api/subscriptions/draft", json={"description": "关注Agent论文"})

    assert response.status_code == 503


def test_draft_subscription_accepts_partial_current_fields(client: TestClient) -> None:
    response = client.post(
        "/api/subscriptions/draft",
        json={"description": "关注Agent论文", "current": {"keywords": ["Agent"]}},
    )

    assert response.status_code == 503


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


def test_subscription_presets_expose_research_engineering_and_people_radar(client: TestClient) -> None:
    response = client.get("/api/subscription-presets")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [
        "research-radar",
        "engineering-radar",
        "people-insights",
    ]
    assert response.json()[0]["kind"] == "paper"
    assert "arXiv" in response.json()[0]["sources"]


def test_apply_subscription_preset_is_idempotent(client: TestClient) -> None:
    first = client.post("/api/subscription-presets/research-radar")
    second = client.post("/api/subscription-presets/research-radar")

    assert first.status_code == 200
    assert first.json()["created"] is True
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert first.json()["subscription"]["id"] == second.json()["subscription"]["id"]

