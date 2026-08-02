from fastapi.testclient import TestClient


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

