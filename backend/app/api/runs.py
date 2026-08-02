from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Subscription, TaskRun
from app.schemas import TaskRunPage, TaskRunResponse

router = APIRouter(prefix="/api", tags=["runs"])


@router.post(
    "/subscriptions/{subscription_id}/run",
    response_model=TaskRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def queue_subscription_run(
    subscription_id: int,
    db: Session = Depends(get_db),
) -> TaskRun:
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
    return task


@router.get("/runs", response_model=TaskRunPage)
def list_runs(
    db: Session = Depends(get_db),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TaskRunPage:
    total = db.scalar(select(func.count()).select_from(TaskRun)) or 0
    records = db.scalars(
        select(TaskRun).order_by(TaskRun.started_at.desc()).limit(limit).offset(offset)
    ).all()
    return TaskRunPage(
        items=[TaskRunResponse.model_validate(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}", response_model=TaskRunResponse)
def get_run(run_id: int, db: Session = Depends(get_db)) -> TaskRun:
    record = db.get(TaskRun, run_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return record

