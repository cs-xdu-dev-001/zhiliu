from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import SearchBriefingResult, SearchItemResult, SearchResponse
from app.services.search import SearchService


router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def search_content(
    q: str = Query(min_length=2, max_length=200),
    kind: str | None = Query(default=None, pattern="^(news|paper|job)$"),
    days: int | None = Query(default=None, ge=1, le=3650),
    limit: int = Query(default=10, ge=1, le=20),
    db: Session = Depends(get_db),
) -> SearchResponse:
    result = SearchService(db).search(q, kind=kind, days=days, limit=limit)
    return SearchResponse(
        query=result.query,
        items=[
            SearchItemResult(
                id=hit.result_id,
                kind=hit.kind,
                title=hit.title,
                summary=hit.summary,
                source=hit.source or "",
                url=hit.source_url or "",
                created_at=hit.created_at,
            )
            for hit in result.items
        ],
        briefings=[
            SearchBriefingResult(
                id=hit.result_id,
                kind=hit.kind,
                title=hit.title,
                summary=hit.summary,
                item_count=hit.item_count or 0,
                created_at=hit.created_at,
            )
            for hit in result.briefings
        ],
        item_total=result.item_total,
        briefing_total=result.briefing_total,
    )
