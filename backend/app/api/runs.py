from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.config import Settings, get_settings
from app.models import Briefing, HermesPublication, Subscription, TaskRun
from app.schemas import TaskRunPage, TaskRunResponse
from app.services.hermes_notify import requeue_notification

router = APIRouter(prefix="/api", tags=["runs"])


def _task_run_response(
    record: TaskRun,
    subscription: Subscription | None,
    publication: HermesPublication | None,
) -> TaskRunResponse:
    return TaskRunResponse(
        id=record.id,
        subscription_id=record.subscription_id,
        retry_of_id=record.retry_of_id,
        hermes_run_id=record.hermes_run_id,
        trace_id=record.trace_id,
        origin=record.origin,
        topic=record.topic or (subscription.name if subscription else None),
        request_summary=record.request_summary,
        status=record.status,
        stage=record.stage,
        result_summary=record.result_summary,
        started_at=record.started_at,
        heartbeat_at=record.heartbeat_at,
        finished_at=record.finished_at,
        cancelled_at=record.cancelled_at,
        duration_ms=record.duration_ms,
        error_message=record.error_message,
        subscription_name=subscription.name if subscription else None,
        publication_id=publication.id if publication else None,
        briefing_id=publication.briefing_id if publication else None,
        retry_count=record.retry_count,
        notification_status=record.notification_status,
        notification_error=record.notification_error,
        notification_sent_at=record.notification_sent_at,
    )


def serialize_task_run(db: Session, record: TaskRun) -> TaskRunResponse:
    publication = db.scalar(
        select(HermesPublication)
        .where(HermesPublication.task_run_id == record.id)
        .order_by(HermesPublication.id.desc())
        .limit(1)
    )
    subscription = db.get(Subscription, record.subscription_id)
    return _task_run_response(record, subscription, publication)


def serialize_task_runs(db: Session, records: list[TaskRun]) -> list[TaskRunResponse]:
    if not records:
        return []
    subscriptions = {
        subscription.id: subscription
        for subscription in db.scalars(
            select(Subscription).where(
                Subscription.id.in_({record.subscription_id for record in records})
            )
        ).all()
    }
    publications: dict[int, HermesPublication] = {}
    for publication in db.scalars(
        select(HermesPublication)
        .where(HermesPublication.task_run_id.in_([record.id for record in records]))
        .order_by(HermesPublication.task_run_id, HermesPublication.id.desc())
    ):
        if publication.task_run_id is not None:
            publications.setdefault(publication.task_run_id, publication)
    return [
        _task_run_response(
            record,
            subscriptions.get(record.subscription_id),
            publications.get(record.id),
        )
        for record in records
    ]


@router.post(
    "/subscriptions/{subscription_id}/run",
    response_model=TaskRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def queue_subscription_run(
    subscription_id: int,
    db: Session = Depends(get_db),
) -> TaskRunResponse:
    subscription = db.get(Subscription, subscription_id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订阅不存在")

    active = db.scalar(
        select(TaskRun).where(
            TaskRun.subscription_id == subscription_id,
            TaskRun.status.in_(("queued", "running")),
        )
    )
    if active is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该订阅已有任务在执行")

    task = TaskRun(subscription_id=subscription_id, status="queued")
    db.add(task)
    db.commit()
    db.refresh(task)
    return serialize_task_run(db, task)


@router.post(
    "/runs/{run_id}/retry",
    response_model=TaskRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_failed_run(run_id: int, db: Session = Depends(get_db)) -> TaskRunResponse:
    original = db.get(TaskRun, run_id)
    if original is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    if original.status != "failed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="仅失败任务可以重新执行")
    if original.origin == "weixin-hermes":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="微信任务请在微信中重新发送请求")
    if original.origin == "web-report" and db.scalar(
        select(Briefing.id).where(
            Briefing.series_id == original.report_series_id,
            Briefing.version_number == original.report_version_number,
        )
    ) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该版本报告已经生成")

    existing_retry = db.scalar(
        select(TaskRun).where(
            TaskRun.retry_of_id == run_id,
            TaskRun.status.in_(("queued", "running")),
        )
    )
    if existing_retry is not None:
        return serialize_task_run(db, existing_retry)

    active = db.scalar(
        select(TaskRun).where(
            TaskRun.subscription_id == original.subscription_id,
            TaskRun.status.in_(("queued", "running")),
        )
    )
    if active is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该订阅已有任务在执行")

    retry = TaskRun(
        subscription_id=original.subscription_id,
        retry_of_id=original.id,
        origin=original.origin,
        topic=original.topic,
        request_summary=original.request_summary,
        status="queued",
        stage="accepted",
        report_item_ids_json=original.report_item_ids_json,
        report_series_id=original.report_series_id,
        report_version_number=original.report_version_number,
    )
    db.add(retry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raced = db.scalar(
            select(TaskRun).where(
                TaskRun.retry_of_id == run_id,
                TaskRun.status.in_(("queued", "running")),
            )
        )
        if raced is not None:
            return serialize_task_run(db, raced)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="重试任务与现有任务冲突")
    db.refresh(retry)
    return serialize_task_run(db, retry)


@router.post("/runs/{run_id}/notify", response_model=TaskRunResponse)
def retry_weixin_notification(
    run_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TaskRunResponse:
    record = db.get(TaskRun, run_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    if record.status != "success":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有已完成任务可以重试微信推送")
    try:
        requeue_notification(db, record, settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return serialize_task_run(db, record)


@router.post("/runs/{run_id}/cancel", response_model=TaskRunResponse)
def cancel_queued_run(run_id: int, db: Session = Depends(get_db)) -> TaskRunResponse:
    record = db.get(TaskRun, run_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    if record.status == "cancelled":
        return serialize_task_run(db, record)
    if record.status != "queued":
        detail = "任务已开始执行，当前无法安全取消" if record.status == "running" else "任务已经结束"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    now = datetime.now(timezone.utc)
    record.status = "cancelled"
    record.stage = "cancelled"
    record.cancelled_at = now
    record.finished_at = now
    record.duration_ms = max(0, int((now - record.started_at).total_seconds() * 1000))
    record.error_message = None
    db.commit()
    return serialize_task_run(db, record)


@router.get("/runs", response_model=TaskRunPage)
def list_runs(
    db: Session = Depends(get_db),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    run_status: Literal["queued", "running", "success", "failed", "cancelled"] | None = Query(default=None, alias="status"),
    origin: Literal["weixin-hermes", "subscription-hermes", "web-report"] | None = Query(default=None),
) -> TaskRunPage:
    filters = []
    if run_status:
        filters.append(TaskRun.status == run_status)
    if origin:
        filters.append(TaskRun.origin == origin)
    total = db.scalar(select(func.count()).select_from(TaskRun).where(*filters)) or 0
    records = db.scalars(
        select(TaskRun)
        .where(*filters)
        .order_by(TaskRun.started_at.desc(), TaskRun.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return TaskRunPage(
        items=serialize_task_runs(db, records),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}", response_model=TaskRunResponse)
def get_run(run_id: int, db: Session = Depends(get_db)) -> TaskRunResponse:
    record = db.get(TaskRun, run_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return serialize_task_run(db, record)

