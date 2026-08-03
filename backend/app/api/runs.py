from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import HermesPublication, Subscription, TaskRun
from app.schemas import TaskRunPage, TaskRunResponse

router = APIRouter(prefix="/api", tags=["runs"])


def _task_run_response(
    record: TaskRun,
    subscription: Subscription | None,
    publication: HermesPublication | None,
) -> TaskRunResponse:
    return TaskRunResponse(
        id=record.id,
        subscription_id=record.subscription_id,
        hermes_run_id=record.hermes_run_id,
        trace_id=record.trace_id,
        origin=record.origin,
        topic=record.topic or (subscription.name if subscription else None),
        request_summary=record.request_summary,
        status=record.status,
        stage=record.stage,
        result_summary=record.result_summary,
        started_at=record.started_at,
        finished_at=record.finished_at,
        duration_ms=record.duration_ms,
        error_message=record.error_message,
        subscription_name=subscription.name if subscription else None,
        publication_id=publication.id if publication else None,
        briefing_id=publication.briefing_id if publication else None,
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


@router.get("/runs", response_model=TaskRunPage)
def list_runs(
    db: Session = Depends(get_db),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    run_status: Literal["queued", "running", "success", "failed"] | None = Query(default=None, alias="status"),
) -> TaskRunPage:
    filters = [TaskRun.status == run_status] if run_status else []
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

