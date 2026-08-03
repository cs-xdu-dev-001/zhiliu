from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Briefing, HermesPublication, IntelligenceItem, PublicationItem
from app.schemas import (
    BriefingDetailResponse,
    BriefingPage,
    BriefingResponse,
    PublicationSummaryResponse,
    SourceItemResponse,
)

router = APIRouter(prefix="/api/briefings", tags=["briefings"])


@router.get("", response_model=BriefingPage)
def list_briefings(
    db: Session = Depends(get_db),
    kind: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> BriefingPage:
    filters = [Briefing.kind == kind] if kind else []
    total = db.scalar(select(func.count()).select_from(Briefing).where(*filters)) or 0
    records = db.scalars(
        select(Briefing).where(*filters).order_by(Briefing.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return BriefingPage(items=[BriefingResponse.model_validate(record) for record in records], total=total, limit=limit, offset=offset)


@router.get("/{briefing_id}", response_model=BriefingDetailResponse)
def get_briefing(briefing_id: int, db: Session = Depends(get_db)) -> BriefingDetailResponse:
    record = db.get(Briefing, briefing_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="简报不存在")
    publication = db.scalar(
        select(HermesPublication)
        .where(HermesPublication.briefing_id == briefing_id)
        .order_by(HermesPublication.created_at, HermesPublication.id)
        .limit(1)
    )
    source_items: list[SourceItemResponse] = []
    publication_response = None
    if publication is not None:
        rows = db.execute(
            select(PublicationItem, IntelligenceItem)
            .join(IntelligenceItem, IntelligenceItem.id == PublicationItem.item_id)
            .where(PublicationItem.publication_id == publication.id)
            .order_by(PublicationItem.ordinal)
        ).all()
        source_items = [
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
        ]
        publication_response = PublicationSummaryResponse.model_validate(publication)
    return BriefingDetailResponse(
        **BriefingResponse.model_validate(record).model_dump(),
        source_items=source_items,
        publication=publication_response,
        trace_available=publication is not None,
    )

