from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Briefing, HermesPublication, IntelligenceItem, PublicationItem, TaskRun
from app.services.hermes import HermesBriefing, HermesItem, HermesResult
from app.services.run_service import RunService, item_fingerprint


class FakeHermesClient:
    async def execute(self, prompt: str) -> HermesResult:
        assert "检索" in prompt
        return HermesResult(
            run_id="run_demo",
            briefing=HermesBriefing(
                title="AI日报",
                kind="news",
                content="今日Agent工具调用引人关注。",
                period_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
                period_end=datetime(2026, 8, 2, tzinfo=timezone.utc),
            ),
            items=[
                HermesItem(
                    kind="news",
                    title="Agent框架发布新版本",
                    summary="工具调用可靠性提升。",
                    url="https://example.com/new-agent",
                    source="Example Research",
                    published_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                    keywords=["Agent"],
                    reason="值得持续跟踪",
                    importance=0.88,
                )
            ],
            raw_output="raw-json",
        )


@pytest.mark.asyncio
async def test_run_service_persists_result_and_completes_task(
    db_session: Session,
    subscription,
) -> None:
    task = TaskRun(subscription_id=subscription.id, status="queued")
    db_session.add(task)
    db_session.commit()

    await RunService(db_session, FakeHermesClient()).execute_task(task.id)
    db_session.refresh(task)

    assert task.status == "success"
    assert task.hermes_run_id == "run_demo"
    assert db_session.scalar(select(func.count()).select_from(IntelligenceItem)) == 1
    assert db_session.scalar(select(func.count()).select_from(Briefing)) == 1
    publication = db_session.scalar(select(HermesPublication))
    link = db_session.scalar(select(PublicationItem))
    assert publication.origin == "subscription-hermes"
    assert publication.trace_id == f"task-run:{task.id}"
    assert publication.hermes_run_id == "run_demo"
    assert publication.task_run_id == task.id
    assert publication.briefing_id is not None
    assert link.publication_id == publication.id
    assert link.was_inserted is True


@pytest.mark.asyncio
async def test_run_service_does_not_overwrite_existing_item_state(
    db_session: Session,
    subscription,
) -> None:
    existing = IntelligenceItem(
        subscription_id=subscription.id,
        kind="news",
        title="Agent框架发布新版本",
        summary="old",
        url="https://example.com/new-agent",
        source="Example Research",
        keywords_json="[]",
        reason="old",
        importance=0.5,
        fingerprint=item_fingerprint("Agent框架发布新版本", "https://example.com/new-agent"),
        is_saved=True,
    )
    task = TaskRun(subscription_id=subscription.id, status="queued")
    db_session.add_all([existing, task])
    db_session.commit()

    await RunService(db_session, FakeHermesClient()).execute_task(task.id)
    db_session.refresh(existing)

    assert db_session.scalar(select(func.count()).select_from(IntelligenceItem)) == 1
    assert existing.is_saved is True
    assert existing.summary == "old"
    publication = db_session.scalar(select(HermesPublication))
    link = db_session.scalar(select(PublicationItem))
    assert publication.item_count == 0
    assert publication.skipped_count == 1
    assert link.item_id == existing.id
    assert link.was_inserted is False


@pytest.mark.asyncio
async def test_run_service_reuses_merge_target_instead_of_audit_source(
    db_session: Session,
    subscription,
) -> None:
    source = IntelligenceItem(
        subscription_id=subscription.id,
        kind="news",
        title="Agent框架发布新版本",
        summary="旧记录",
        url="https://example.com/new-agent",
        source="Example Research",
        keywords_json="[]",
        fingerprint=item_fingerprint("Agent框架发布新版本", "https://example.com/new-agent"),
        is_invalid=True,
    )
    target = IntelligenceItem(
        subscription_id=subscription.id,
        kind="news",
        title="Agent框架正式版本",
        summary="保留记录",
        url="https://example.com/canonical-agent",
        source="Example Research",
        keywords_json="[]",
        fingerprint=item_fingerprint("Agent框架正式版本", "https://example.com/canonical-agent"),
    )
    db_session.add_all([source, target])
    db_session.flush()
    source.merged_into_id = target.id
    task = TaskRun(subscription_id=subscription.id, status="queued")
    db_session.add(task)
    db_session.commit()

    await RunService(db_session, FakeHermesClient()).execute_task(task.id)

    link = db_session.scalar(select(PublicationItem))
    assert link.item_id == target.id

