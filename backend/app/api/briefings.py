from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
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
    kind: Literal["news", "paper", "job"] | None = None,
    q: str | None = Query(default=None, max_length=200),
    days: int | None = Query(default=None, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> BriefingPage:
    filters = [Briefing.kind == kind] if kind else []
    normalized_q = q.strip() if q else ""
    if normalized_q:
        escaped_q = normalized_q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped_q}%"
        filters.append(or_(Briefing.title.ilike(pattern, escape="\\"), Briefing.content.ilike(pattern, escape="\\")))
    if days is not None:
        filters.append(Briefing.created_at >= datetime.now(timezone.utc) - timedelta(days=days))
    total = db.scalar(select(func.count()).select_from(Briefing).where(*filters)) or 0
    records = db.scalars(
        select(Briefing)
        .where(*filters)
        .order_by(Briefing.created_at.desc(), Briefing.id.desc())
        .limit(limit)
        .offset(offset)
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
                is_invalid=item.is_invalid,
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

