from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ItemTopic, Topic
from app.services.topics import ensure_topic, link_item_topics, normalize_topic


def test_topic_normalization_unifies_spacing_and_width() -> None:
    assert normalize_topic("  ＡＩ-Agent / RAG  ") == "ai agent rag"


def test_topic_list_detail_and_state(client: TestClient, db_session: Session, seeded_item) -> None:
    topic = ensure_topic(db_session, "Agent")
    link_item_topics(db_session, seeded_item)
    db_session.commit()

    listed = client.get("/api/topics", params={"q": "agent"})
    detail = client.get(f"/api/topics/{topic.id}")
    updated = client.patch(f"/api/topics/{topic.id}", json={"isFollowed": True, "isPinned": True})

    assert listed.status_code == 200
    matched = next(row for row in listed.json()["items"] if row["id"] == topic.id)
    assert matched["itemCount30Days"] == 1
    assert detail.status_code == 200
    assert detail.json()["latestItems"][0]["id"] == seeded_item.id
    assert updated.json()["isFollowed"] is True
    assert updated.json()["isPinned"] is True


def test_topic_merge_moves_item_links(client: TestClient, db_session: Session, seeded_item) -> None:
    source = ensure_topic(db_session, "LLM Agent")
    target = ensure_topic(db_session, "Agent")
    db_session.add(ItemTopic(item_id=seeded_item.id, topic_id=source.id))
    db_session.commit()

    response = client.post(f"/api/topics/{source.id}/merge", json={"targetId": target.id})

    assert response.status_code == 200
    db_session.refresh(source)
    assert source.merged_into_id == target.id
    assert db_session.query(ItemTopic).filter_by(item_id=seeded_item.id, topic_id=target.id).count() == 1
    assert client.get(f"/api/topics/{source.id}").status_code == 404
