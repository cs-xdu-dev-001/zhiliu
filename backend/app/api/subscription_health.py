from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from croniter import croniter
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import HermesPublication, Subscription, TaskRun
from app.schemas import SubscriptionHealthPage, SubscriptionHealthResponse

router = APIRouter(prefix="/api/subscription-health", tags=["subscription-health"])


def serialize(db: Session, subscription: Subscription) -> SubscriptionHealthResponse:
    since = datetime.now(timezone.utc) - timedelta(days=30)
    runs = list(db.scalars(select(TaskRun).where(TaskRun.subscription_id == subscription.id, TaskRun.started_at >= since).order_by(TaskRun.started_at.desc())).all())
    success = sum(run.status == "success" for run in runs)
    failed = sum(run.status == "failed" for run in runs)
    consecutive = 0
    for run in runs:
        if run.status != "failed":
            break
        consecutive += 1
    durations = [run.duration_ms for run in runs if run.duration_ms is not None]
    produced = db.scalar(select(func.coalesce(func.sum(HermesPublication.item_count), 0)).where(HermesPublication.subscription_id == subscription.id, HermesPublication.created_at >= since)) or 0
    next_run = None
    if subscription.enabled:
        next_run = croniter(subscription.schedule, datetime.now(ZoneInfo("Asia/Shanghai"))).get_next(datetime)
    return SubscriptionHealthResponse(
        subscription_id=subscription.id,
        name=subscription.name,
        kind=subscription.kind,
        enabled=subscription.enabled,
        next_run_at=next_run,
        last_success_at=next((run.finished_at for run in runs if run.status == "success"), None),
        last_failure_at=next((run.finished_at for run in runs if run.status == "failed"), None),
        run_count=len(runs),
        success_count=success,
        failed_count=failed,
        success_rate=round(success / len(runs), 3) if runs else None,
        consecutive_failures=consecutive,
        average_duration_ms=round(sum(durations) / len(durations)) if durations else None,
        produced_item_count=int(produced),
    )


@router.get("", response_model=SubscriptionHealthPage)
def subscription_health(db: Session = Depends(get_db)) -> SubscriptionHealthPage:
    subscriptions = db.scalars(select(Subscription).where(Subscription.id > 0).order_by(Subscription.enabled.desc(), Subscription.created_at.desc())).all()
    items = [serialize(db, subscription) for subscription in subscriptions]
    return SubscriptionHealthPage(items=items, generated_at=datetime.now(timezone.utc))
