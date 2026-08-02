from fastapi.testclient import TestClient


def test_list_items_and_mark_read(client: TestClient, seeded_item) -> None:
    listed = client.get("/api/items?kind=news&state=unread")
    updated = client.patch(
        f"/api/items/{seeded_item.id}",
        json={"isRead": True},
    )

    assert listed.status_code == 200
    assert listed.json()["items"][0]["title"] == "Agent框架发布新版本"
    assert listed.json()["total"] == 1
    assert updated.status_code == 200
    assert updated.json()["isRead"] is True


def test_dashboard_reports_unread_count(client: TestClient, seeded_item) -> None:
    response = client.get("/api/dashboard")

    assert response.status_code == 200
    assert response.json()["unreadCount"] == 1
    assert response.json()["topItems"][0]["importance"] == 0.92


def test_missing_item_returns_not_found(client: TestClient) -> None:
    response = client.patch("/api/items/999", json={"isSaved": True})

    assert response.status_code == 404


def test_get_item_detail(client: TestClient, seeded_item) -> None:
    response = client.get(f"/api/items/{seeded_item.id}")

    assert response.status_code == 200
    assert response.json()["id"] == seeded_item.id
    assert response.json()["title"] == "Agent框架发布新版本"
    assert response.json()["reason"] == "影响Agent开发工作流"


def test_missing_item_detail_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/items/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "情报不存在"

