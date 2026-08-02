from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Briefing
from app.schemas import BriefingPage, BriefingResponse

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


@router.get("/{briefing_id}", response_model=BriefingResponse)
def get_briefing(briefing_id: int, db: Session = Depends(get_db)) -> Briefing:
    record = db.get(Briefing, briefing_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="简报不存在")
    return record

