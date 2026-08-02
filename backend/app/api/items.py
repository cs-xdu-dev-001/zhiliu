import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Briefing, IntelligenceItem, Subscription, TaskRun
from app.schemas import (
    BriefingResponse,
    DashboardResponse,
    IntelligenceItemResponse,
    ItemPage,
    ItemStateUpdate,
)

router = APIRouter(prefix="/api", tags=["intelligence"])


def serialize_item(record: IntelligenceItem) -> IntelligenceItemResponse:
    return IntelligenceItemResponse(
        id=record.id,
        subscription_id=record.subscription_id,
        kind=record.kind,
        title=record.title,
        summary=record.summary,
        url=record.url,
        source=record.source,
        published_at=record.published_at,
        keywords=json.loads(record.keywords_json),
        reason=record.reason,
        importance=record.importance,
        is_read=record.is_read,
        is_saved=record.is_saved,
        is_ignored=record.is_ignored,
        created_at=record.created_at,
    )


@router.get("/items", response_model=ItemPage)
def list_items(
    db: Session = Depends(get_db),
    kind: str | None = None,
    state: Literal["unread", "saved", "ignored"] | None = None,
    subscription_id: int | None = Query(default=None, alias="subscriptionId"),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ItemPage:
    filters = []
    if kind:
        filters.append(IntelligenceItem.kind == kind)
    if subscription_id:
        filters.append(IntelligenceItem.subscription_id == subscription_id)
    if state == "unread":
        filters.extend([IntelligenceItem.is_read.is_(False), IntelligenceItem.is_ignored.is_(False)])
    elif state == "saved":
        filters.append(IntelligenceItem.is_saved.is_(True))
    elif state == "ignored":
        filters.append(IntelligenceItem.is_ignored.is_(True))

    total = db.scalar(select(func.count()).select_from(IntelligenceItem).where(*filters)) or 0
    records = db.scalars(
        select(IntelligenceItem)
        .where(*filters)
        .order_by(IntelligenceItem.importance.desc(), IntelligenceItem.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return ItemPage(items=[serialize_item(record) for record in records], total=total, limit=limit, offset=offset)


@router.patch("/items/{item_id}", response_model=IntelligenceItemResponse)
def update_item_state(
    item_id: int,
    payload: ItemStateUpdate,
    db: Session = Depends(get_db),
) -> IntelligenceItemResponse:
    record = db.get(IntelligenceItem, item_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="情报不存在")
    for field in ("is_read", "is_saved", "is_ignored"):
        value = getattr(payload, field)
        if value is not None:
            setattr(record, field, value)
    db.commit()
    db.refresh(record)
    return serialize_item(record)


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(db: Session = Depends(get_db)) -> DashboardResponse:
    unread_count = db.scalar(
        select(func.count()).select_from(IntelligenceItem).where(
            IntelligenceItem.is_read.is_(False), IntelligenceItem.is_ignored.is_(False)
        )
    ) or 0
    saved_count = db.scalar(
        select(func.count()).select_from(IntelligenceItem).where(IntelligenceItem.is_saved.is_(True))
    ) or 0
    active_subscriptions = db.scalar(
        select(func.count()).select_from(Subscription).where(Subscription.enabled.is_(True))
    ) or 0
    failed_runs = db.scalar(
        select(func.count()).select_from(TaskRun).where(TaskRun.status == "failed")
    ) or 0
    top_items = db.scalars(
        select(IntelligenceItem)
        .where(IntelligenceItem.is_read.is_(False), IntelligenceItem.is_ignored.is_(False))
        .order_by(IntelligenceItem.importance.desc())
        .limit(3)
    ).all()
    latest = db.scalar(select(Briefing).order_by(Briefing.created_at.desc()).limit(1))
    latest_response = BriefingResponse.model_validate(latest) if latest else None
    return DashboardResponse(
        unread_count=unread_count,
        saved_count=saved_count,
        active_subscriptions=active_subscriptions,
        failed_runs=failed_runs,
        top_items=[serialize_item(record) for record in top_items],
        latest_briefing=latest_response,
    )

