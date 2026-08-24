from fastapi.testclient import TestClient


def test_saved_view_crud_normalizes_and_whitelists_query(client: TestClient) -> None:
    created = client.post(
        "/api/saved-views",
        json={
            "name": "  待读论文  ",
            "query": "?state=unread&state=saved&kind=paper&tag=重点&page=4",
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "待读论文"
    assert body["query"] == "state=unread&state=saved&kind=paper&tag=%E9%87%8D%E7%82%B9"
    assert client.get("/api/saved-views").json()[0]["id"] == body["id"]

    updated = client.put(
        f"/api/saved-views/{body['id']}",
        json={"name": "论文重点", "query": "sort=newest&days=7"},
    )
    assert updated.status_code == 200
    assert updated.json()["query"] == "sort=newest&days=7"
    assert client.delete(f"/api/saved-views/{body['id']}").status_code == 204
    assert client.get("/api/saved-views").json() == []


def test_saved_view_rejects_invalid_name_query_and_duplicate(client: TestClient) -> None:
    payload = {"name": "近期情报", "query": "days=7"}
    assert client.post("/api/saved-views", json=payload).status_code == 201
    assert client.post("/api/saved-views", json=payload).status_code == 409
    assert client.post("/api/saved-views", json={"name": "   ", "query": ""}).status_code == 422
    assert client.post(
        "/api/saved-views",
        json={"name": "危险参数", "query": "redirect=https%3A%2F%2Fevil.example"},
    ).status_code == 422
