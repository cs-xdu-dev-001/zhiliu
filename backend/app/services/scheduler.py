from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import Subscription, TaskRun
from app.services.hermes import HermesBriefing, HermesItem, HermesResult, HermesUnavailable
from app.core.crypto import SecretDecryptionError
from app.cron_utils import normalize_weekday_for_apscheduler
from app.services.hermes_integration import HermesIntegrationService
from app.services.run_service import RunService
from app.services.report_service import ReportService

_scheduler: AsyncIOScheduler | None = None
_last_queue_poll_at: datetime | None = None
_last_queue_poll_failed = False
_last_sweep_at: datetime | None = None
_last_sweep_lost_count = 0


def scheduler_snapshot(*, enabled: bool) -> dict[str, object]:
    """Return a non-sensitive runtime summary for operational diagnostics."""
    running = bool(_scheduler is not None and _scheduler.running)
    return {
        "enabled": enabled,
        "running": running,
        "job_count": len(_scheduler.get_jobs()) if running and _scheduler is not None else 0,
        "last_queue_poll_at": _last_queue_poll_at,
        "last_queue_poll_failed": _last_queue_poll_failed,
        "last_sweep_at": _last_sweep_at,
        "last_sweep_lost_count": _last_sweep_lost_count,
    }


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

    async def execute(self, _: str, heartbeat=None) -> HermesResult:
        if heartbeat is not None:
            await heartbeat()
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

    async def execute_report(self, _: str, heartbeat=None):
        if heartbeat is not None:
            await heartbeat()
        from app.services.hermes import HermesReport

        now = datetime.now(timezone.utc)
        return HermesReport(
            run_id=f"demo-report-{int(now.timestamp())}",
            title="所选情报专题报告",
            kind=self.subscription.kind,
            content="当前为演示模式。报告依据所选情报整理。[1]",
            raw_output='{"mode":"demo-report"}',
        )


async def process_queued_tasks() -> None:
    global _last_queue_poll_at, _last_queue_poll_failed
    _last_queue_poll_at = datetime.now(timezone.utc)
    try:
        sweep_lost_tasks()
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
                claimed = db.execute(
                    update(TaskRun)
                    .where(TaskRun.id == task_id, TaskRun.status == "queued")
                    .values(status="running", stage="accepted", heartbeat_at=datetime.now(timezone.utc))
                )
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                if claimed.rowcount != 1:
                    continue
                db.refresh(task)
                try:
                    client = HermesIntegrationService(db, settings).resolve_client(task.subscription, DemoHermesClient)
                except (HermesUnavailable, SecretDecryptionError) as exc:
                    task.status = "failed"
                    task.stage = "failed"
                    task.heartbeat_at = datetime.now(timezone.utc)
                    task.error_message = str(exc)[:2000]
                    task.finished_at = datetime.now(timezone.utc)
                    task.duration_ms = 0
                    try:
                        db.commit()
                    except Exception:
                        db.rollback()
                        raise
                    continue
                if task.origin == "web-report":
                    await ReportService(db, client).execute_task(task.id)
                else:
                    await RunService(db, client).execute_task(task.id)
    except Exception:
        _last_queue_poll_failed = True
        raise
    else:
        _last_queue_poll_failed = False


def sweep_lost_tasks() -> int:
    global _last_sweep_at, _last_sweep_lost_count
    settings = get_settings()
    stale_after = max(settings.hermes_timeout_seconds * 2, 600)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after)
    with SessionLocal() as db:
        records = db.scalars(
            select(TaskRun).where(
                TaskRun.status == "running",
                or_(
                    TaskRun.heartbeat_at < cutoff,
                    (TaskRun.heartbeat_at.is_(None) & (TaskRun.started_at < cutoff)),
                ),
            )
        ).all()
        now = datetime.now(timezone.utc)
        for task in records:
            task.status = "failed"
            task.stage = "lost"
            task.error_message = "任务长时间未上报进度，可能已中断"
            task.finished_at = now
            task.duration_ms = max(0, int((now - task.started_at).total_seconds() * 1000))
        if records:
            db.commit()
        _last_sweep_at = now
        _last_sweep_lost_count = len(records)
        return _last_sweep_lost_count


def refresh_subscription_jobs() -> None:
    if _scheduler is None:
        return
    for job in _scheduler.get_jobs():
        if job.id.startswith("subscription:"):
            _scheduler.remove_job(job.id)

    with SessionLocal() as db:
        subscriptions = db.scalars(select(Subscription).where(Subscription.enabled.is_(True))).all()
        for subscription in subscriptions:
            try:
                trigger = CronTrigger.from_crontab(normalize_weekday_for_apscheduler(subscription.schedule), timezone="Asia/Shanghai")
            except ValueError:
                continue
            _scheduler.add_job(
                queue_subscription_by_id,
                trigger,
                args=[subscription.id],
                id=f"subscription:{subscription.id}",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )


def refresh_subscription_job(subscription_id: int) -> None:
    if _scheduler is None:
        return
    job_id = f"subscription:{subscription_id}"
    with SessionLocal() as db:
        subscription = db.get(Subscription, subscription_id)
        if subscription is None or not subscription.enabled:
            if _scheduler.get_job(job_id) is not None:
                _scheduler.remove_job(job_id)
            return
        try:
            trigger = CronTrigger.from_crontab(normalize_weekday_for_apscheduler(subscription.schedule), timezone="Asia/Shanghai")
        except ValueError:
            if _scheduler.get_job(job_id) is not None:
                _scheduler.remove_job(job_id)
            return
        _scheduler.add_job(
            queue_subscription_by_id,
            trigger,
            args=[subscription.id],
            id=job_id,
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

