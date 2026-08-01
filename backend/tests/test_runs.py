from fastapi.testclient import TestClient


def test_manual_run_queues_task(auth_client: TestClient, subscription) -> None:
    response = auth_client.post(f"/api/subscriptions/{subscription.id}/run")
    listed = auth_client.get("/api/runs?limit=1")

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert listed.status_code == 200
    assert listed.json()["items"][0]["subscriptionId"] == subscription.id


def test_duplicate_active_run_is_rejected(auth_client: TestClient, running_task) -> None:
    response = auth_client.post(f"/api/subscriptions/{running_task.subscription_id}/run")

    assert response.status_code == 409


def test_run_list_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/runs")

    assert response.status_code == 401

