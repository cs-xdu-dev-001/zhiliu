from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    Briefing,
    HermesPublication,
    IntelligenceItem,
    PublicationItem,
    Subscription,
    TaskRun,
)
from app.schemas import (
    PublicationTraceResponse,
    SourceItemResponse,
    TraceBriefingResponse,
    TraceSubscriptionResponse,
    TraceTaskRunResponse,
)


router = APIRouter(prefix="/api/publications", tags=["publications"])


@router.get("/{publication_id}/trace", response_model=PublicationTraceResponse)
def get_publication_trace(
    publication_id: int,
    db: Session = Depends(get_db),
) -> PublicationTraceResponse:
    publication = db.get(HermesPublication, publication_id)
    if publication is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="追踪记录不存在",
        )

    subscription = db.get(Subscription, publication.subscription_id)
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="追踪记录关联的订阅不存在",
        )
    task = db.get(TaskRun, publication.task_run_id) if publication.task_run_id else None
    briefing = db.get(Briefing, publication.briefing_id) if publication.briefing_id else None
    rows = db.execute(
        select(PublicationItem, IntelligenceItem)
        .join(IntelligenceItem, IntelligenceItem.id == PublicationItem.item_id)
        .where(PublicationItem.publication_id == publication.id)
        .order_by(PublicationItem.ordinal)
    ).all()

    return PublicationTraceResponse(
        publication_id=publication.id,
        trace_id=publication.trace_id,
        origin=publication.origin,
        request_summary=publication.request_summary,
        hermes_run_id=publication.hermes_run_id,
        created_at=publication.created_at,
        item_count=publication.item_count,
        skipped_count=publication.skipped_count,
        subscription=TraceSubscriptionResponse(id=subscription.id, name=subscription.name),
        task_run=TraceTaskRunResponse.model_validate(task) if task else None,
        items=[
            SourceItemResponse(
                id=item.id,
                title=item.title,
                summary=item.summary,
                source=item.source,
                url=item.url,
                ordinal=link.ordinal,
                was_inserted=link.was_inserted,
            )
            for link, item in rows
        ],
        briefing=TraceBriefingResponse.model_validate(briefing) if briefing else None,
    )
