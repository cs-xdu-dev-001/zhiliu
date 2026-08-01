import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import CurrentUser
from app.db import get_db
from app.models import Subscription
from app.schemas import SubscriptionPayload, SubscriptionResponse

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


def serialize_subscription(record: Subscription) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=record.id,
        name=record.name,
        kind=record.kind,
        keywords=json.loads(record.keywords_json),
        schedule=record.schedule,
        prompt=record.prompt,
        enabled=record.enabled,
        last_run_at=record.last_run_at,
        next_run_at=record.next_run_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("", response_model=list[SubscriptionResponse])
def list_subscriptions(_: CurrentUser, db: Session = Depends(get_db)) -> list[SubscriptionResponse]:
    records = db.scalars(select(Subscription).order_by(Subscription.created_at.desc())).all()
    return [serialize_subscription(record) for record in records]


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
def create_subscription(
    payload: SubscriptionPayload,
    _: CurrentUser,
    db: Session = Depends(get_db),
) -> SubscriptionResponse:
    record = Subscription(
        name=payload.name,
        kind=payload.kind,
        keywords_json=json.dumps(payload.keywords, ensure_ascii=False),
        schedule=payload.schedule,
        prompt=payload.prompt,
        enabled=payload.enabled,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return serialize_subscription(record)


def get_subscription_or_404(db: Session, subscription_id: int) -> Subscription:
    record = db.get(Subscription, subscription_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订阅不存在")
    return record


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
def get_subscription(subscription_id: int, _: CurrentUser, db: Session = Depends(get_db)) -> SubscriptionResponse:
    return serialize_subscription(get_subscription_or_404(db, subscription_id))


@router.put("/{subscription_id}", response_model=SubscriptionResponse)
def update_subscription(
    subscription_id: int,
    payload: SubscriptionPayload,
    _: CurrentUser,
    db: Session = Depends(get_db),
) -> SubscriptionResponse:
    record = get_subscription_or_404(db, subscription_id)
    record.name = payload.name
    record.kind = payload.kind
    record.keywords_json = json.dumps(payload.keywords, ensure_ascii=False)
    record.schedule = payload.schedule
    record.prompt = payload.prompt
    record.enabled = payload.enabled
    db.commit()
    db.refresh(record)
    return serialize_subscription(record)


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription(
    subscription_id: int,
    _: CurrentUser,
    db: Session = Depends(get_db),
) -> Response:
    record = get_subscription_or_404(db, subscription_id)
    db.delete(record)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

