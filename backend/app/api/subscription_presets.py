import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Subscription
from app.schemas import SubscriptionPayload, SubscriptionPresetApplyResponse, SubscriptionPresetResponse
from app.services.scheduler import refresh_subscription_job
from app.subscription_presets import SUBSCRIPTION_PRESETS, SubscriptionPreset, get_subscription_preset
from app.api.subscriptions import serialize_subscription

router = APIRouter(prefix="/api/subscription-presets", tags=["subscription-presets"])


def serialize_preset(preset: SubscriptionPreset) -> SubscriptionPresetResponse:
    return SubscriptionPresetResponse(
        id=preset.id,
        name=preset.name,
        kind=preset.kind,
        keywords=list(preset.keywords),
        schedule=preset.schedule,
        prompt=preset.prompt,
        description=preset.description,
        sources=list(preset.sources),
    )


@router.get("", response_model=list[SubscriptionPresetResponse])
def list_subscription_presets() -> list[SubscriptionPresetResponse]:
    return [serialize_preset(preset) for preset in SUBSCRIPTION_PRESETS]


@router.post("/{preset_id}", response_model=SubscriptionPresetApplyResponse)
def apply_subscription_preset(
    preset_id: str,
    payload: SubscriptionPayload | None = None,
    db: Session = Depends(get_db),
) -> SubscriptionPresetApplyResponse:
    preset = get_subscription_preset(preset_id)
    if preset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订阅模板不存在")

    values = payload or SubscriptionPayload(
        name=preset.name, kind=preset.kind, keywords=list(preset.keywords),
        schedule=preset.schedule, prompt=preset.prompt,
    )
    # Serialize the lookup and insert across concurrent SQLite writers.
    db.execute(text("BEGIN IMMEDIATE"))
    try:
        existing = db.scalar(
            select(Subscription).where(
                Subscription.name == values.name,
                Subscription.kind == values.kind,
            ).order_by(Subscription.id)
        )
        if existing is not None:
            subscription = serialize_subscription(existing)
            db.commit()
            return SubscriptionPresetApplyResponse(
                preset_id=preset.id, created=False, subscription=subscription,
            )

        record = Subscription(
            name=values.name,
            kind=values.kind,
            keywords_json=json.dumps(values.keywords, ensure_ascii=False),
            schedule=values.schedule,
            prompt=values.prompt,
            enabled=values.enabled,
            notify_wechat=values.notify_wechat,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        refresh_subscription_job(record.id)
        return SubscriptionPresetApplyResponse(
            preset_id=preset.id,
            created=True,
            subscription=serialize_subscription(record),
        )
    except Exception:
        db.rollback()
        raise
