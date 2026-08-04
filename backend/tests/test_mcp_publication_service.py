from copy import deepcopy

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.mcp_server.schemas import TaskFailurePayload, TaskStartPayload, PublishPayload
from app.mcp_server.service import (
    AUTO_PROMPT,
    AUTO_SCHEDULE,
    AUTO_SUBSCRIPTION_IDS,
    PublicationConflict,
    PublicationFailure,
    PublicationService,
    TaskFeedbackService,
)
from app.models import Briefing, HermesPublication, IntelligenceItem, PublicationItem, Subscription, TaskRun
from app.services.run_service import item_fingerprint


def publish_payload(**changes) -> PublishPayload:
    data = {
        "idempotencyKey": "wx-agent-20260802",
        "traceId": "trace-agent-20260802",
        "hermesRunId": "hermes-run-agent-1",
        "topic": "Agent更新",
        "kind": "news",
        "requestSummary": "整理后放进知流",
        "items": [
            {
                "title": "Agent框架更新",
                "summary": "工具调用能力提升。",
                "url": "https://example.com/agent/",
                "source": "Example",
                "keywords": ["Agent"],
                "reason": "值得关注",
                "importance": 0.9,
            }
        ],
        "briefing": {"title": "Agent更新简报", "content": "本次更新集中在工具调用。"},
    }
    data.update(deepcopy(changes))
    return PublishPayload.model_validate(data)


def test_weixin_task_moves_from_processing_to_completed(db_session: Session) -> None:
    feedback = TaskFeedbackService(db_session, public_base_url="https://zhiliu.example")
    started = feedback.begin(
        TaskStartPayload(
            traceId="trace-agent-20260802",
            hermesRunId="hermes-run-agent-1",
            topic="Agent更新",
            kind="news",
            requestSummary="整理后放进知流",
        )
    )

    assert started.status == "running"
    assert started.stage == "processing"
    assert started.task_url == f"https://zhiliu.example/tasks/{started.task_run_id}"
    task = db_session.get(TaskRun, started.task_run_id)
    assert task.origin == "weixin-hermes"

    receipt = PublicationService(
        db_session,
        public_base_url="https://zhiliu.example",
    ).publish(publish_payload())
    db_session.refresh(task)

    assert task.status == "success"
    assert task.stage == "completed"
    assert task.finished_at is not None
    assert task.result_summary == "新增1条情报，复用0条，生成报告《微信整理 · Agent更新简报》"
    assert receipt.task_run_id == task.id
    assert receipt.trace_url == f"https://zhiliu.example/traces/{receipt.receipt_id}"
    assert receipt.task_url == f"https://zhiliu.example/tasks/{task.id}"
    assert receipt.briefing_url == f"https://zhiliu.example/reports/{receipt.briefing_id}"
    assert receipt.message == task.result_summary
    publication = db_session.get(HermesPublication, receipt.receipt_id)
    assert publication.task_run_id == task.id
    repeated = feedback.begin(
        TaskStartPayload(
            traceId="trace-agent-20260802",
            hermesRunId="hermes-run-agent-1",
            topic="Agent更新",
            kind="news",
            requestSummary="整理后放进知流",
        )
    )
    assert repeated.status == "success"
    assert repeated.stage == "completed"
    assert repeated.duplicate is True


def test_weixin_task_failure_is_visible_and_idempotent(db_session: Session) -> None:
    feedback = TaskFeedbackService(db_session)
    started = feedback.begin(
        TaskStartPayload(
            traceId="trace-failed-20260802",
            topic="失败任务",
            kind="paper",
            requestSummary="检索论文后放进知流",
        )
    )
    repeated = feedback.begin(
        TaskStartPayload(
            traceId="trace-failed-20260802",
            topic="失败任务",
            kind="paper",
            requestSummary="检索论文后放进知流",
        )
    )
    failed = feedback.fail(
        TaskFailurePayload(
            traceId="trace-failed-20260802",
            errorMessage="来源网站暂时不可达",
        )
    )

    assert repeated.task_run_id == started.task_run_id
    assert repeated.duplicate is True
    assert failed.status == "failed"
    task = db_session.get(TaskRun, started.task_run_id)
    assert task.stage == "failed"
    assert task.error_message == "来源网站暂时不可达"


def test_publish_persists_visible_content_atomically(db_session: Session) -> None:
    receipt = PublicationService(db_session).publish(publish_payload())
    item = db_session.scalar(select(IntelligenceItem))
    briefing = db_session.scalar(select(Briefing))
    category = db_session.get(Subscription, item.subscription_id)

    assert receipt.item_count == 1
    assert receipt.trace_id == "trace-agent-20260802"
    assert receipt.briefing_id == briefing.id
    assert item.source == "Example · 微信Hermes"
    assert item.url == "https://example.com/agent"
    assert briefing.title == "微信整理 · Agent更新简报"
    assert category.name == "微信整理·情报"
    assert category.enabled is False
    assert db_session.scalar(select(func.count()).select_from(HermesPublication)) == 1
    publication = db_session.scalar(select(HermesPublication))
    link = db_session.scalar(select(PublicationItem))
    assert publication.trace_id == "trace-agent-20260802"
    assert publication.hermes_run_id == "hermes-run-agent-1"
    assert link.item_id == item.id
    assert link.ordinal == 0
    assert link.was_inserted is True


def test_same_key_and_payload_returns_original_receipt(db_session: Session) -> None:
    service = PublicationService(db_session)
    first = service.publish(publish_payload())
    second = service.publish(publish_payload())

    assert second.receipt_id == first.receipt_id
    assert second.duplicate is True


def test_same_payload_with_new_key_returns_original_receipt(db_session: Session) -> None:
    service = PublicationService(db_session)
    first = service.publish(publish_payload())
    second = service.publish(publish_payload(idempotencyKey="wx-agent-retry-new-key"))

    assert second.receipt_id == first.receipt_id
    assert second.duplicate is True


def test_semantically_equal_url_and_keywords_share_payload_hash(db_session: Session) -> None:
    service = PublicationService(db_session)
    retry_data = publish_payload().model_dump(mode="json", by_alias=True, exclude_none=True)
    retry_data["idempotencyKey"] = "wx-agent-canonical-retry"
    retry_data["items"][0]["url"] = "https://example.com/agent"
    retry_data["items"][0]["keywords"] = ["RAG", "Agent"]
    original_data = publish_payload().model_dump(mode="json", by_alias=True, exclude_none=True)
    original_data["items"][0]["keywords"] = ["Agent", "RAG"]

    canonical_first = service.publish(PublishPayload.model_validate(original_data))
    second = service.publish(PublishPayload.model_validate(retry_data))

    assert second.receipt_id == canonical_first.receipt_id
    assert second.duplicate is True


def test_same_key_with_changed_payload_is_rejected(db_session: Session) -> None:
    service = PublicationService(db_session)
    service.publish(publish_payload())

    with pytest.raises(PublicationConflict, match="幂等键已用于不同内容"):
        service.publish(publish_payload(topic="被修改的主题"))


def test_existing_item_is_counted_as_skipped(db_session: Session) -> None:
    service = PublicationService(db_session)
    first = service.publish(publish_payload(briefing=None))
    second_payload = publish_payload(
        idempotencyKey="another-publish",
        traceId="trace-another-publish",
        topic="另一批",
        briefing=None,
    )
    second = service.publish(second_payload)

    assert first.item_count == 1
    assert second.item_count == 0
    assert second.skipped_count == 1
    links = db_session.scalars(
        select(PublicationItem).order_by(PublicationItem.publication_id)
    ).all()
    assert len(links) == 2
    assert links[0].item_id == links[1].item_id
    assert links[1].was_inserted is False


def test_existing_merged_item_resolves_to_retained_target(db_session: Session) -> None:
    service = PublicationService(db_session)
    service.publish(publish_payload(briefing=None))
    source = db_session.scalar(select(IntelligenceItem))
    target = IntelligenceItem(
        subscription_id=source.subscription_id,
        kind="news",
        title="Agent框架保留版本",
        summary="保留记录",
        url="https://example.com/agent-canonical",
        source="Example · 微信Hermes",
        keywords_json="[]",
        fingerprint=item_fingerprint("Agent框架保留版本", "https://example.com/agent-canonical"),
    )
    db_session.add(target)
    db_session.flush()
    source.is_invalid = True
    source.merged_into_id = target.id
    db_session.commit()

    receipt = service.publish(publish_payload(
        idempotencyKey="merged-item-republish",
        traceId="trace-merged-item-republish",
        briefing=None,
    ))
    link = db_session.scalar(
        select(PublicationItem).where(PublicationItem.publication_id == receipt.receipt_id)
    )

    assert link.item_id == target.id
    assert receipt.item_count == 0
    assert receipt.skipped_count == 1


def test_briefing_counts_all_linked_items_including_reused(
    db_session: Session,
) -> None:
    service = PublicationService(db_session)
    service.publish(publish_payload(briefing=None))

    receipt = service.publish(
        publish_payload(
            idempotencyKey="report-with-reused-item",
            traceId="trace-report-with-reused-item",
        )
    )
    briefing = db_session.get(Briefing, receipt.briefing_id)

    assert receipt.item_count == 0
    assert receipt.skipped_count == 1
    assert briefing.item_count == 1


def test_concurrent_item_fingerprint_conflict_retries_as_skip(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PublicationService(db_session)
    resolve_items = service._resolve_items
    first_attempt = True

    def collide_once(
        subscription_id: int,
        payload: PublishPayload,
    ) -> list[tuple[IntelligenceItem, bool]]:
        nonlocal first_attempt
        if first_attempt:
            first_attempt = False
            result = resolve_items(subscription_id, payload)
            db_session.flush()
            db_session.commit()
            raise IntegrityError(
                "insert",
                {},
                RuntimeError(
                    "UNIQUE constraint failed: intelligence_items.fingerprint"
                ),
            )
        return resolve_items(subscription_id, payload)

    monkeypatch.setattr(service, "_resolve_items", collide_once)

    receipt = service.publish(publish_payload())

    assert receipt.item_count == 0
    assert receipt.skipped_count == 1
    assert db_session.scalar(select(func.count()).select_from(IntelligenceItem)) == 1
    assert db_session.scalar(select(func.count()).select_from(HermesPublication)) == 1


def test_existing_system_category_is_reused_and_repaired(db_session: Session) -> None:
    category = Subscription(
        id=AUTO_SUBSCRIPTION_IDS["news"],
        name="微信整理·情报",
        kind="news",
        keywords_json='["被修改"]',
        schedule="0 8 * * *",
        prompt="被修改的提示词",
        enabled=True,
    )
    db_session.add(category)
    db_session.commit()

    PublicationService(db_session).publish(publish_payload())

    categories = db_session.scalars(
        select(Subscription).where(
            Subscription.name == "微信整理·情报",
            Subscription.kind == "news",
        )
    ).all()
    assert len(categories) == 1
    assert categories[0].keywords_json == "[]"
    assert categories[0].schedule == AUTO_SCHEDULE
    assert categories[0].prompt == AUTO_PROMPT
    assert categories[0].enabled is False


def test_user_category_with_reserved_name_is_not_hijacked(db_session: Session) -> None:
    user_category = Subscription(
        name="微信整理·情报",
        kind="news",
        keywords_json='["用户"]',
        schedule="0 9 * * *",
        prompt="用户自己的订阅",
        enabled=True,
    )
    db_session.add(user_category)
    db_session.commit()

    PublicationService(db_session).publish(publish_payload())

    db_session.refresh(user_category)
    system_category = db_session.get(Subscription, AUTO_SUBSCRIPTION_IDS["news"])
    assert system_category is not None
    assert system_category.id != user_category.id
    assert user_category.prompt == "用户自己的订阅"
    assert user_category.enabled is True


def test_unrelated_integrity_error_is_reported_as_safe_failure(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PublicationService(db_session)

    def fail_commit() -> None:
        raise IntegrityError("insert", {}, RuntimeError("database detail"))

    monkeypatch.setattr(db_session, "commit", fail_commit)

    with pytest.raises(PublicationFailure, match="发布失败，未写入知流") as raised:
        service.publish(publish_payload())

    assert "database detail" not in str(raised.value)


def test_unrelated_integrity_error_is_not_retried_when_item_already_exists(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PublicationService(db_session)
    service.publish(publish_payload(briefing=None))
    commit_calls = 0
    original_commit = db_session.commit

    def fail_once() -> None:
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 1:
            raise IntegrityError("insert", {}, RuntimeError("other unique constraint"))
        original_commit()

    monkeypatch.setattr(db_session, "commit", fail_once)

    with pytest.raises(PublicationFailure, match="发布失败，未写入知流"):
        service.publish(
            publish_payload(
                idempotencyKey="different-publication",
                topic="另一批",
                briefing=None,
            )
        )

    assert commit_calls == 1


def test_failure_rolls_back_items_briefing_and_receipt(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PublicationService(db_session)

    def fail_receipt(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "_create_receipt", fail_receipt)

    with pytest.raises(PublicationFailure, match="发布失败，未写入知流"):
        service.publish(publish_payload())

    assert db_session.scalar(select(func.count()).select_from(IntelligenceItem)) == 0
    assert db_session.scalar(select(func.count()).select_from(Briefing)) == 0
    assert db_session.scalar(select(func.count()).select_from(HermesPublication)) == 0
    assert db_session.scalar(select(func.count()).select_from(Subscription)) == 0


def test_receipt_failure_before_commit_rolls_back_everything(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PublicationService(db_session)

    def fail_receipt(*_args, **_kwargs):
        raise RuntimeError("receipt boom")

    monkeypatch.setattr(service, "_receipt", fail_receipt)

    with pytest.raises(PublicationFailure, match="发布失败，未写入知流"):
        service.publish(publish_payload())

    assert db_session.scalar(select(func.count()).select_from(IntelligenceItem)) == 0
    assert db_session.scalar(select(func.count()).select_from(Briefing)) == 0
    assert db_session.scalar(select(func.count()).select_from(HermesPublication)) == 0
    assert db_session.scalar(select(func.count()).select_from(Subscription)) == 0
