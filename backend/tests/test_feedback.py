from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mcp_server.schemas import PublishPayload
from app.mcp_server.service import PublicationService
from app.models import Briefing, ContentFeedback, HermesPreference, IntelligenceItem, ItemTopic
from app.services.preferences import PreferenceService
from app.services.topics import ensure_topic


def feedback_payload(item_id: int, feedback_type: str, key: str, **extra):
    return {
        "targetType": "item",
        "targetId": item_id,
        "feedbackType": feedback_type,
        "idempotencyKey": key,
        **extra,
    }


def test_feedback_is_queryable_idempotent_and_changes_explainable_score(client, seeded_item) -> None:
    payload = feedback_payload(seeded_item.id, "useful", "feedback-useful-1")

    first = client.post("/api/feedback", json=payload)
    repeated = client.post("/api/feedback", json=payload)
    listed = client.get("/api/feedback", params={"itemId": seeded_item.id})
    item = client.get(f"/api/items/{seeded_item.id}").json()

    assert first.status_code == 201
    assert repeated.json()["id"] == first.json()["id"]
    assert len(listed.json()["items"]) == 1
    assert item["personalizedScore"] == 0.97
    assert item["recommendationReasons"][0]["code"] == "feedback_useful"
    conflict = client.post("/api/feedback", json={**payload, "feedbackType": "irrelevant"})
    assert conflict.status_code == 422


def test_feedback_history_requires_exactly_one_target_filter(client, seeded_item) -> None:
    assert client.get("/api/feedback").status_code == 422
    assert client.get("/api/feedback", params={"itemId": seeded_item.id, "briefingId": 1}).status_code == 422


def test_conflicting_feedback_revoke_restore_and_version_checks(client, db_session: Session, seeded_item) -> None:
    useful = client.post("/api/feedback", json=feedback_payload(seeded_item.id, "useful", "feedback-useful-2")).json()
    irrelevant = client.post("/api/feedback", json=feedback_payload(seeded_item.id, "irrelevant", "feedback-irrelevant-1")).json()

    db_session.refresh(seeded_item)
    assert seeded_item.is_ignored is True
    assert db_session.get(ContentFeedback, useful["id"]).active is False
    revoked = client.post(f"/api/feedback/{irrelevant['id']}/revoke", json={"version": irrelevant["version"]})
    db_session.refresh(seeded_item)
    assert revoked.json()["active"] is False
    assert seeded_item.is_ignored is False

    stale = client.post(f"/api/feedback/{irrelevant['id']}/restore", json={"version": irrelevant["version"]})
    assert stale.status_code == 409
    restored = client.post(f"/api/feedback/{irrelevant['id']}/restore", json={"version": revoked.json()["version"]})
    db_session.refresh(seeded_item)
    assert restored.json()["active"] is True
    assert seeded_item.is_ignored is True


def test_same_type_replaces_previous_effect_without_leaving_stale_state(client, db_session: Session, seeded_item) -> None:
    first = client.post("/api/feedback", json=feedback_payload(
        seeded_item.id, "irrelevant", "feedback-irrelevant-repeat-1"
    )).json()
    second = client.post("/api/feedback", json=feedback_payload(
        seeded_item.id, "irrelevant", "feedback-irrelevant-repeat-2"
    )).json()
    useful = client.post("/api/feedback", json=feedback_payload(
        seeded_item.id, "useful", "feedback-useful-after-repeat"
    )).json()

    db_session.refresh(seeded_item)
    assert db_session.get(ContentFeedback, first["id"]).active is False
    assert db_session.get(ContentFeedback, second["id"]).active is False
    assert db_session.get(ContentFeedback, useful["id"]).active is True
    assert seeded_item.is_ignored is False


def test_restore_deactivates_newer_conflicting_feedback(client, db_session: Session, seeded_item) -> None:
    useful = client.post("/api/feedback", json=feedback_payload(
        seeded_item.id, "useful", "feedback-restore-conflict-useful"
    )).json()
    irrelevant = client.post("/api/feedback", json=feedback_payload(
        seeded_item.id, "irrelevant", "feedback-restore-conflict-irrelevant"
    )).json()
    useful_record = db_session.get(ContentFeedback, useful["id"])
    restored = client.post(f"/api/feedback/{useful_record.id}/restore", json={"version": useful_record.version})

    assert restored.status_code == 200
    db_session.refresh(seeded_item)
    assert db_session.get(ContentFeedback, irrelevant["id"]).active is False
    assert restored.json()["active"] is True
    assert seeded_item.is_ignored is False


def test_summary_feedback_requires_note_and_can_be_edited(client, seeded_item) -> None:
    missing = client.post("/api/feedback", json=feedback_payload(seeded_item.id, "summary_wrong", "feedback-summary-1"))
    assert missing.status_code == 422

    created = client.post("/api/feedback", json=feedback_payload(
        seeded_item.id,
        "summary_wrong",
        "feedback-summary-2",
        note="遗漏了发布时间",
    )).json()
    updated = client.patch(f"/api/feedback/{created['id']}", json={"version": created["version"], "note": "遗漏发布时间和适用范围"})

    assert updated.status_code == 200
    assert updated.json()["note"] == "遗漏发布时间和适用范围"
    assert updated.json()["version"] == 2


def test_failed_long_term_feedback_rolls_back_and_can_be_retried(client, db_session: Session, seeded_item) -> None:
    failed = client.post("/api/feedback", json=feedback_payload(
        seeded_item.id,
        "follow_up",
        "feedback-follow-up-without-topic",
        applyLongTerm=True,
    ))

    assert failed.status_code == 422
    assert db_session.scalar(select(ContentFeedback).where(
        ContentFeedback.idempotency_key == "feedback-follow-up-without-topic"
    )) is None

    retried = client.post("/api/feedback", json=feedback_payload(
        seeded_item.id,
        "useful",
        "feedback-follow-up-without-topic",
    ))
    assert retried.status_code == 201


def test_revoked_feedback_can_be_submitted_again_with_a_new_key(client, seeded_item) -> None:
    first = client.post("/api/feedback", json=feedback_payload(
        seeded_item.id, "useful", "feedback-resubmit-first"
    )).json()
    revoked = client.post(f"/api/feedback/{first['id']}/revoke", json={"version": first["version"]}).json()
    repeated = client.post("/api/feedback", json=feedback_payload(
        seeded_item.id, "useful", "feedback-resubmit-first"
    )).json()
    resubmitted = client.post("/api/feedback", json=feedback_payload(
        seeded_item.id, "useful", "feedback-resubmit-second"
    )).json()

    assert repeated["id"] == first["id"]
    assert repeated["active"] is False
    assert repeated["version"] == revoked["version"]
    assert resubmitted["id"] != first["id"]
    assert resubmitted["active"] is True


def test_report_feedback_is_stored_without_mutating_source_items(client, db_session: Session, subscription, seeded_item) -> None:
    report = Briefing(subscription_id=subscription.id, title="Agent报告", kind="news", content="结论", item_count=1)
    db_session.add(report)
    db_session.commit()

    response = client.post("/api/feedback", json={
        "targetType": "briefing",
        "targetId": report.id,
        "feedbackType": "useful",
        "idempotencyKey": "feedback-report-useful",
    })

    assert response.status_code == 201
    assert response.json()["briefingId"] == report.id
    assert response.json()["itemId"] is None
    db_session.refresh(seeded_item)
    assert seeded_item.personalized_score is None
    assert all(
        not reason["code"].startswith("feedback_")
        for reason in client.get(f"/api/items/{seeded_item.id}").json()["recommendationReasons"]
    )
    rejected = client.post("/api/feedback", json={
        "targetType": "briefing",
        "targetId": report.id,
        "feedbackType": "follow_up",
        "applyLongTerm": True,
        "idempotencyKey": "feedback-report-long-term",
    })
    assert rejected.status_code == 422


def test_explicit_follow_up_feedback_reaches_hermes_preference_and_new_item_reason(
    client,
    db_session: Session,
    subscription,
    seeded_item,
) -> None:
    topic = ensure_topic(db_session, "Agent")
    db_session.add(ItemTopic(item_id=seeded_item.id, topic_id=topic.id))
    db_session.commit()
    feedback = client.post("/api/feedback", json=feedback_payload(
        seeded_item.id,
        "follow_up",
        "feedback-follow-up-chain",
        applyLongTerm=True,
    )).json()

    preference = db_session.get(HermesPreference, feedback["preferenceId"])
    assert feedback["impactScope"] == "long_term"
    assert preference.active is True
    assert PreferenceService(db_session).list(kind="news")[0].id == preference.id

    receipt = PublicationService(db_session).publish(PublishPayload.model_validate({
        "idempotencyKey": "feedback-chain-publication",
        "traceId": "feedback-chain-trace",
        "topic": "Agent持续进展",
        "kind": "news",
        "requestSummary": "按有效偏好继续整理Agent",
        "items": [{
            "title": "Agent后续版本",
            "summary": "出现新的可靠性能力。",
            "url": "https://example.com/agent-follow-up",
            "source": "Example",
            "keywords": ["Agent"],
            "importance": 0.7,
        }],
    }))
    new_item = db_session.scalar(select(IntelligenceItem).where(IntelligenceItem.title == "Agent后续版本"))
    payload = client.get(f"/api/items/{new_item.id}").json()
    reason = next(value for value in payload["recommendationReasons"] if value["code"] == "topic_prefer")

    assert receipt.item_count == 1
    assert reason["preferenceId"] == preference.id
    revoked = client.post(f"/api/feedback/{feedback['id']}/revoke", json={"version": feedback["version"]})
    assert revoked.status_code == 200
    db_session.refresh(preference)
    assert preference.active is False
    assert all(value["preferenceId"] != preference.id for value in client.get(f"/api/items/{new_item.id}").json()["recommendationReasons"])


def test_revoked_feedback_cannot_reactivate_long_term_preference_via_edit(
    client,
    db_session: Session,
    seeded_item,
) -> None:
    topic = ensure_topic(db_session, "安全更新")
    db_session.add(ItemTopic(item_id=seeded_item.id, topic_id=topic.id))
    db_session.commit()
    created = client.post("/api/feedback", json=feedback_payload(
        seeded_item.id,
        "follow_up",
        "feedback-inactive-long-term",
        applyLongTerm=True,
    )).json()
    revoked = client.post(f"/api/feedback/{created['id']}/revoke", json={"version": created["version"]}).json()
    edited = client.patch(f"/api/feedback/{created['id']}", json={
        "version": revoked["version"],
        "applyLongTerm": True,
    })

    assert edited.status_code == 422
    preference = db_session.get(HermesPreference, created["preferenceId"])
    db_session.refresh(preference)
    assert preference.active is False


def test_feedback_does_not_take_ownership_of_an_existing_preference(
    client,
    db_session: Session,
    seeded_item,
) -> None:
    topic = ensure_topic(db_session, "既有关注")
    db_session.add(ItemTopic(item_id=seeded_item.id, topic_id=topic.id))
    db_session.commit()
    preference, _ = PreferenceService(db_session).save(
        scope="topic", effect="prefer", value=topic.name, kind="all", note="用户原有说明"
    )
    created = client.post("/api/feedback", json=feedback_payload(
        seeded_item.id,
        "follow_up",
        "feedback-existing-preference",
        applyLongTerm=True,
    )).json()
    revoked = client.post(f"/api/feedback/{created['id']}/revoke", json={"version": created["version"]})

    assert created["preferenceId"] == preference.id
    assert revoked.status_code == 200
    db_session.refresh(preference)
    assert preference.active is True
    assert preference.note == "用户原有说明"
