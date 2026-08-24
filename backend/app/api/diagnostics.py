from datetime import datetime, timezone
from time import perf_counter

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db import get_db
from app.models import HermesIntegration, HermesPublication, TaskRun
from app.schemas import ApiModel
from app.services.scheduler import scheduler_snapshot

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


class DatabaseDiagnostics(ApiModel):
    status: str
    latency_ms: int | None = None
    migration_version: str | None = None


class QueueDiagnostics(ApiModel):
    queued: int
    running: int
    oldest_active_seconds: int | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None


class HermesDiagnostics(ApiModel):
    configured: bool
    status: str
    checked_at: datetime | None = None


class SchedulerDiagnostics(ApiModel):
    enabled: bool
    running: bool
    job_count: int
    last_queue_poll_at: datetime | None = None
    last_queue_poll_failed: bool
    last_sweep_at: datetime | None = None
    last_sweep_lost_count: int


class McpDiagnostics(ApiModel):
    status: str
    last_write_at: datetime | None = None
    last_task_status: str | None = None
    last_task_at: datetime | None = None


class DiagnosticsResponse(ApiModel):
    status: str
    generated_at: datetime
    database: DatabaseDiagnostics
    scheduler: SchedulerDiagnostics
    queue: QueueDiagnostics
    hermes: HermesDiagnostics
    mcp: McpDiagnostics


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@router.get("", response_model=DiagnosticsResponse)
def diagnostics(
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DiagnosticsResponse:
    generated_at = datetime.now(timezone.utc)
    started = perf_counter()
    try:
        db.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return DiagnosticsResponse(
            status="unavailable",
            generated_at=generated_at,
            database=DatabaseDiagnostics(status="unavailable"),
            scheduler=SchedulerDiagnostics(**scheduler_snapshot(enabled=settings.scheduler_enabled)),
            queue=QueueDiagnostics(queued=0, running=0),
            hermes=HermesDiagnostics(configured=False, status="unknown"),
            mcp=McpDiagnostics(status="unknown"),
        )

    database = DatabaseDiagnostics(status="ok", latency_ms=max(0, round((perf_counter() - started) * 1000)))
    try:
        database.migration_version = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one_or_none()
    except SQLAlchemyError:
        db.rollback()

    status_counts = dict(
        db.execute(
            select(TaskRun.status, func.count(TaskRun.id)).group_by(TaskRun.status)
        ).all()
    )
    oldest_active = db.scalar(
        select(func.min(TaskRun.started_at)).where(TaskRun.status.in_(("queued", "running")))
    )
    last_success = db.scalar(select(func.max(TaskRun.finished_at)).where(TaskRun.status == "success"))
    last_failure = db.scalar(select(func.max(TaskRun.finished_at)).where(TaskRun.status == "failed"))
    oldest_active_utc = _as_utc(oldest_active)
    integration = db.get(HermesIntegration, 1)
    last_mcp_write = db.scalar(select(func.max(HermesPublication.created_at)))
    last_mcp_task = db.scalar(
        select(TaskRun)
        .where(TaskRun.origin == "weixin-hermes")
        .order_by(TaskRun.started_at.desc(), TaskRun.id.desc())
        .limit(1)
    )
    hermes_configured = bool(
        (integration is not None and integration.encrypted_api_key)
        or settings.hermes_api_key.strip()
        or settings.demo_mode
    )
    hermes_status = integration.last_status if integration is not None else (
        "configured" if settings.hermes_api_key.strip() else "demo" if settings.demo_mode else "unconfigured"
    )
    runtime = scheduler_snapshot(enabled=settings.scheduler_enabled)
    overall_status = "ok"
    if settings.scheduler_enabled and not runtime["running"]:
        overall_status = "degraded"
    if int(status_counts.get("failed", 0)) > 0 and _as_utc(last_failure) and (
        _as_utc(last_success) is None or _as_utc(last_failure) > _as_utc(last_success)
    ):
        overall_status = "degraded"
    last_mcp_write_utc = _as_utc(last_mcp_write)
    last_mcp_task_at = _as_utc(last_mcp_task.started_at) if last_mcp_task is not None else None
    mcp_status = "verified" if last_mcp_write_utc is not None else "unverified"
    if (
        last_mcp_task is not None
        and last_mcp_task.status == "failed"
        and (last_mcp_write_utc is None or (last_mcp_task_at is not None and last_mcp_task_at > last_mcp_write_utc))
    ):
        mcp_status = "failed"
        overall_status = "degraded"

    return DiagnosticsResponse(
        status=overall_status,
        generated_at=generated_at,
        database=database,
        scheduler=SchedulerDiagnostics(**runtime),
        queue=QueueDiagnostics(
            queued=int(status_counts.get("queued", 0)),
            running=int(status_counts.get("running", 0)),
            oldest_active_seconds=(
                max(0, int((generated_at - oldest_active_utc).total_seconds()))
                if oldest_active_utc is not None
                else None
            ),
            last_success_at=_as_utc(last_success),
            last_failure_at=_as_utc(last_failure),
        ),
        hermes=HermesDiagnostics(
            configured=hermes_configured,
            status=hermes_status,
            checked_at=_as_utc(integration.last_checked_at) if integration is not None else None,
        ),
        mcp=McpDiagnostics(
            status=mcp_status,
            last_write_at=last_mcp_write_utc,
            last_task_status=last_mcp_task.status if last_mcp_task is not None else None,
            last_task_at=last_mcp_task_at,
        ),
    )
