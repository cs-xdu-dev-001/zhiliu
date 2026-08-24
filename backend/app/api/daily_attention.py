from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.briefings import _queue_report
from app.api.items import serialize_item
from app.api.runs import serialize_task_run
from app.db import get_db
from app.models import Briefing, HermesPublication, TaskRun
from app.schemas import (
    BriefingResponse,
    DailyAttentionGenerateResponse,
    DailyAttentionItemResponse,
    DailyAttentionResponse,
    DailyAttentionSettingsResponse,
    DailyAttentionSettingsUpdate,
    DailyAttentionTopicResponse,
)
from app.services.daily_attention import build_instruction, build_snapshot

router = APIRouter(prefix="/api/daily-attention", tags=["daily-attention"])


def _response(db: Session) -> DailyAttentionResponse:
    snapshot = build_snapshot(db)
    active = db.scalar(select(TaskRun).where(TaskRun.trace_id == snapshot.idempotency_key))
    latest = db.scalar(
        select(Briefing)
        .join(HermesPublication, HermesPublication.briefing_id == Briefing.id)
        .outerjoin(TaskRun, TaskRun.id == Briefing.generation_task_id)
        .where(or_(TaskRun.topic == "每日关注摘要", HermesPublication.idempotency_key.like("daily-attention:%")))
        .order_by(Briefing.created_at.desc(), Briefing.id.desc())
        .limit(1)
    )
    return DailyAttentionResponse(
        date=snapshot.day,
        settings=DailyAttentionSettingsResponse(
            min_importance=snapshot.config.daily_min_importance,
            important_only=snapshot.config.daily_important_only,
        ),
        items=[
            DailyAttentionItemResponse(item=serialize_item(item), reasons=snapshot.reasons[item.id])
            for item in snapshot.items
        ],
        rising_topics=[
            DailyAttentionTopicResponse(
                id=topic.id,
                name=topic.name,
                current_count=topic.current_count,
                previous_count=topic.previous_count,
            )
            for topic in snapshot.rising_topics
        ],
        important_change_count=snapshot.important_change_count,
        source_unavailable_count=snapshot.source_unavailable_count,
        pending_change_count=snapshot.pending_change_count,
        consecutive_failure_count=snapshot.consecutive_failure_count,
        actionable_count=snapshot.actionable_count,
        idempotency_key=snapshot.idempotency_key,
        latest_briefing=BriefingResponse.model_validate(latest) if latest else None,
        active_task=serialize_task_run(db, active) if active else None,
    )


@router.get("", response_model=DailyAttentionResponse)
def daily_attention(db: Session = Depends(get_db)) -> DailyAttentionResponse:
    return _response(db)


@router.put("/settings", response_model=DailyAttentionResponse)
def update_daily_attention(
    payload: DailyAttentionSettingsUpdate,
    db: Session = Depends(get_db),
) -> DailyAttentionResponse:
    snapshot = build_snapshot(db)
    snapshot.config.daily_min_importance = payload.min_importance
    snapshot.config.daily_important_only = payload.important_only
    db.commit()
    return _response(db)


@router.post("/generate", response_model=DailyAttentionGenerateResponse, status_code=status.HTTP_202_ACCEPTED)
def generate_daily_attention(db: Session = Depends(get_db)) -> DailyAttentionGenerateResponse:
    snapshot = build_snapshot(db)
    existing = db.scalar(select(TaskRun).where(TaskRun.trace_id == snapshot.idempotency_key))
    if existing is not None:
        return DailyAttentionGenerateResponse(
            created=False,
            message="今日相同范围的关注摘要已生成或正在生成",
            task=serialize_task_run(db, existing),
        )
    if not snapshot.items:
        return DailyAttentionGenerateResponse(
            created=False,
            message="今日没有达到条件的重要变化，未生成空摘要",
        )
    task_response = _queue_report(
        db,
        item_ids=[item.id for item in snapshot.items],
        instruction=build_instruction(snapshot),
        request_id=snapshot.idempotency_key,
        series_id=str(uuid5(NAMESPACE_URL, snapshot.idempotency_key)),
        version_number=1,
        changes_only=False,
    )
    task = db.get(TaskRun, task_response.id)
    if task is not None:
        task.topic = "每日关注摘要"
        db.commit()
        db.refresh(task)
        task_response = serialize_task_run(db, task)
    return DailyAttentionGenerateResponse(created=True, message="每日关注摘要已进入生成队列", task=task_response)
