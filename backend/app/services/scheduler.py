from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import Subscription, TaskRun
from app.services.hermes import HermesBriefing, HermesItem, HermesResult, HermesUnavailable
from app.core.crypto import SecretDecryptionError
from app.services.hermes_integration import HermesIntegrationService
from app.services.run_service import RunService

_scheduler: AsyncIOScheduler | None = None


def queue_subscription(db: Session, subscription_id: int) -> TaskRun:
    active = db.scalar(
        select(TaskRun).where(
            TaskRun.subscription_id == subscription_id,
            TaskRun.status.in_(("queued", "running")),
        )
    )
    if active is not None:
        return active
    task = TaskRun(subscription_id=subscription_id, status="queued")
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def queue_subscription_by_id(subscription_id: int) -> None:
    with SessionLocal() as db:
        if db.get(Subscription, subscription_id) is not None:
            queue_subscription(db, subscription_id)


class DemoHermesClient:
    def __init__(self, subscription: Subscription) -> None:
        self.subscription = subscription

    async def execute(self, _: str) -> HermesResult:
        now = datetime.now(timezone.utc)
        title = f"{self.subscription.name}演示更新"
        return HermesResult(
            run_id=f"demo-{int(now.timestamp())}",
            briefing=HermesBriefing(
                title=f"{self.subscription.name}简报",
                kind=self.subscription.kind,
                content="当前为演示模式。配置Hermes API后，此处将展示真实检索和总结结果。",
                period_start=now,
                period_end=now,
            ),
            items=[
                HermesItem(
                    kind=self.subscription.kind,
                    title=title,
                    summary="这是用于验证任务调度、结果入库和页面刷新的演示情报。",
                    url=f"https://example.com/zhiliu-demo/{self.subscription.id}/{int(now.timestamp())}",
                    source="知流演示",
                    published_at=now,
                    keywords=["演示", self.subscription.kind],
                    reason="验证知流与Hermes的任务链路",
                    importance=0.6,
                )
            ],
            raw_output='{"mode":"demo"}',
        )


async def process_queued_tasks() -> None:
    with SessionLocal() as lookup_db:
        task_ids = list(
            lookup_db.scalars(
                select(TaskRun.id).where(TaskRun.status == "queued").order_by(TaskRun.started_at).limit(3)
            ).all()
        )

    settings = get_settings()
    for task_id in task_ids:
        with SessionLocal() as db:
            task = db.get(TaskRun, task_id)
            if task is None or task.status != "queued":
                continue
            try:
                client = HermesIntegrationService(db, settings).resolve_client(task.subscription, DemoHermesClient)
            except (HermesUnavailable, SecretDecryptionError) as exc:
                task.status = "failed"
                task.error_message = str(exc)[:2000]
                task.finished_at = datetime.now(timezone.utc)
                task.duration_ms = 0
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                continue
            await RunService(db, client).execute_task(task.id)


def refresh_subscription_jobs() -> None:
    if _scheduler is None:
        return
    for job in _scheduler.get_jobs():
        if job.id.startswith("subscription:"):
            _scheduler.remove_job(job.id)

    with SessionLocal() as db:
        subscriptions = db.scalars(select(Subscription).where(Subscription.enabled.is_(True))).all()
        for subscription in subscriptions:
            _scheduler.add_job(
                queue_subscription_by_id,
                CronTrigger.from_crontab(subscription.schedule, timezone="Asia/Shanghai"),
                args=[subscription.id],
                id=f"subscription:{subscription.id}",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler
    _scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    _scheduler.add_job(
        process_queued_tasks,
        "interval",
        seconds=5,
        id="queue-consumer",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        refresh_subscription_jobs,
        "interval",
        seconds=60,
        id="subscription-refresh",
        max_instances=1,
        coalesce=True,
    )
    refresh_subscription_jobs()
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None

