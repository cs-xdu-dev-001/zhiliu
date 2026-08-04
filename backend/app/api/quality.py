from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import HermesPublication, HermesQualityDecision
from app.schemas import QualityDecisionResponse, QualityPage
from app.services.quality import QualityNotFound, QualityRestoreConflict, restore_quality_decision

router = APIRouter(prefix="/api/quality", tags=["quality"])


def serialize(record: HermesQualityDecision) -> QualityDecisionResponse:
    publication = record.publication
    return QualityDecisionResponse(
        id=record.id,
        publication_id=record.publication_id,
        item_id=record.item_id,
        action=record.action,
        reason_code=record.reason_code,
        reason=record.reason,
        kind=record.kind,
        title=record.title,
        summary=record.summary,
        source=record.source,
        url=record.url,
        importance=record.importance,
        restored_at=record.restored_at,
        created_at=record.created_at,
        trace_id=publication.trace_id,
        briefing_id=publication.briefing_id,
    )


@router.get("", response_model=QualityPage)
def list_quality(
    action: str | None = Query(default=None, pattern="^(filtered|duplicate|inserted|accepted|restored)$"),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> QualityPage:
    filters = [HermesQualityDecision.restored_at.is_(None)] if action == "filtered" else []
    if action == "restored":
        filters.append(HermesQualityDecision.restored_at.is_not(None))
    elif action and action != "filtered":
        filters.append(HermesQualityDecision.action == action)
    items = db.scalars(
        select(HermesQualityDecision).where(*filters).order_by(HermesQualityDecision.created_at.desc()).limit(limit)
    ).all()
    total = db.scalar(select(func.count()).select_from(HermesQualityDecision).where(*filters)) or 0
    return QualityPage(
        items=[serialize(item) for item in items],
        total=total,
        filtered_count=db.scalar(select(func.count()).select_from(HermesQualityDecision).where(HermesQualityDecision.action == "filtered", HermesQualityDecision.restored_at.is_(None))) or 0,
        duplicate_count=db.scalar(select(func.count()).select_from(HermesQualityDecision).where(HermesQualityDecision.action == "duplicate")) or 0,
        restored_count=db.scalar(select(func.count()).select_from(HermesQualityDecision).where(HermesQualityDecision.reason_code == "restored")) or 0,
    )


@router.post("/{decision_id}/restore", response_model=QualityDecisionResponse)
def restore_quality(decision_id: int, db: Session = Depends(get_db)) -> QualityDecisionResponse:
    try:
        return serialize(restore_quality_decision(db, decision_id))
    except QualityNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except QualityRestoreConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
