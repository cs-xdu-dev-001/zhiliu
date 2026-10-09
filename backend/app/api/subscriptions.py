import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.config import Settings, get_settings
from app.core.crypto import SecretDecryptionError
from app.models import Subscription
from app.schemas import (SchedulePreviewRequest, SchedulePreviewResponse, SubscriptionDraftRequest,
                         SubscriptionDraftResponse, SubscriptionPayload, SubscriptionResponse)
from app.services.hermes import DemoSubscriptionDraftClient, HermesError, HermesInvalidOutput, HermesTimeout, HermesUnavailable
from app.services.hermes_integration import HermesIntegrationService
from app.services.preferences import PreferenceService
from app.services.scheduler import refresh_subscription_job

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


def serialize_subscription(record: Subscription) -> SubscriptionResponse:
    next_run_at = None
    if record.enabled:
        next_run_at = croniter(record.schedule, datetime.now(ZoneInfo("Asia/Shanghai"))).get_next(datetime)
    return SubscriptionResponse(
        id=record.id,
        name=record.name,
        kind=record.kind,
        keywords=json.loads(record.keywords_json),
        schedule=record.schedule,
        prompt=record.prompt,
        enabled=record.enabled,
        notify_wechat=record.notify_wechat,
        last_run_at=record.last_run_at,
        next_run_at=next_run_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("", response_model=list[SubscriptionResponse])
def list_subscriptions(db: Session = Depends(get_db)) -> list[SubscriptionResponse]:
    records = db.scalars(select(Subscription).order_by(Subscription.created_at.desc())).all()
    return [serialize_subscription(record) for record in records]


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
def create_subscription(
    payload: SubscriptionPayload,
    db: Session = Depends(get_db),
) -> SubscriptionResponse:
    record = Subscription(
        name=payload.name,
        kind=payload.kind,
        keywords_json=json.dumps(payload.keywords, ensure_ascii=False),
        schedule=payload.schedule,
        prompt=payload.prompt,
        enabled=payload.enabled,
        notify_wechat=payload.notify_wechat,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    refresh_subscription_job(record.id)
    return serialize_subscription(record)


def get_subscription_or_404(db: Session, subscription_id: int) -> Subscription:
    record = db.get(Subscription, subscription_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订阅不存在")
    return record


@router.post("/preview-schedule", response_model=SchedulePreviewResponse)
def preview_schedule(payload: SchedulePreviewRequest) -> SchedulePreviewResponse:
    try:
        schedule = SubscriptionPayload.validate_schedule(payload.schedule)
        iterator = croniter(schedule, datetime.now(ZoneInfo("Asia/Shanghai")))
        runs = [iterator.get_next(datetime) for _ in range(3)]
        return SchedulePreviewResponse(valid=True, next_runs=runs)
    except ValueError as exc:
        return SchedulePreviewResponse(valid=False, message=str(exc))


def demo_draft_client(_):
    return DemoSubscriptionDraftClient()


@router.post("/draft", response_model=SubscriptionDraftResponse)
async def draft_subscription(
    payload: SubscriptionDraftRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SubscriptionDraftResponse:
    try:
        client = HermesIntegrationService(db, settings).resolve_client(None, demo_draft_client)
        rules = PreferenceService(db).list(kind=payload.current.kind if payload.current else None) if payload.use_preferences else []
        context = {
            "description": payload.description,
            "current": payload.current.model_dump(exclude_none=True) if payload.current else None,
            "preferences": [{"scope": rule.scope, "effect": rule.effect, "value": rule.value, "kind": rule.kind} for rule in rules[:30]],
        }
        # Do not hold a database read transaction while Hermes drafts the configuration.
        db.rollback()
        return await asyncio.wait_for(client.draft_subscription(json.dumps(context, ensure_ascii=False)), timeout=45)
    except (TimeoutError, HermesTimeout) as exc:
        raise HTTPException(status_code=504, detail="配置生成超时，原有填写内容已保留，可稍后重试") from exc
    except (HermesUnavailable, SecretDecryptionError) as exc:
        raise HTTPException(status_code=503, detail="Hermes暂不可用，请检查连接；可继续使用模板或手动填写") from exc
    except (HermesInvalidOutput, HermesError) as exc:
        raise HTTPException(status_code=502, detail="Hermes未生成有效配置，请调整描述后重试") from exc


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
def get_subscription(subscription_id: int, db: Session = Depends(get_db)) -> SubscriptionResponse:
    return serialize_subscription(get_subscription_or_404(db, subscription_id))


@router.put("/{subscription_id}", response_model=SubscriptionResponse)
def update_subscription(
    subscription_id: int,
    payload: SubscriptionPayload,
    db: Session = Depends(get_db),
) -> SubscriptionResponse:
    record = get_subscription_or_404(db, subscription_id)
    record.name = payload.name
    record.kind = payload.kind
    record.keywords_json = json.dumps(payload.keywords, ensure_ascii=False)
    record.schedule = payload.schedule
    record.prompt = payload.prompt
    record.enabled = payload.enabled
    record.notify_wechat = payload.notify_wechat
    db.commit()
    db.refresh(record)
    refresh_subscription_job(record.id)
    return serialize_subscription(record)


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
) -> Response:
    record = get_subscription_or_404(db, subscription_id)
    record_id = record.id
    db.delete(record)
    db.commit()
    refresh_subscription_job(record_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

