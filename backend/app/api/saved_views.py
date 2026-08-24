from urllib.parse import parse_qsl, urlencode

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SavedView
from app.schemas import SavedViewPayload, SavedViewResponse


router = APIRouter(prefix="/api/saved-views", tags=["saved-views"])

_VALUES = {
    "kind": {"news", "paper", "job"},
    "state": {"all", "unread", "saved", "ignored", "invalid", "stale", "low", "source-unavailable"},
    "sort": {"importance", "newest", "oldest", "title"},
}
_TEXT_LIMITS = {"q": 200, "source": 120, "tag": 40}
_ALLOWED_KEYS = {*_VALUES, *_TEXT_LIMITS, "days", "subscriptionId"}


def normalize_saved_query(value: str) -> str:
    raw = value.removeprefix("?")
    pairs = parse_qsl(raw, keep_blank_values=False, max_num_fields=40)
    normalized: list[tuple[str, str]] = []
    for key, item in pairs:
        item = item.strip()
        if key == "page":
            continue
        if key not in _ALLOWED_KEYS:
            raise ValueError(f"不支持保存筛选参数：{key}")
        if key in _VALUES and item not in _VALUES[key]:
            raise ValueError(f"筛选参数{key}无效")
        if key in _TEXT_LIMITS and (not item or len(item) > _TEXT_LIMITS[key]):
            raise ValueError(f"筛选参数{key}无效")
        if key in {"days", "subscriptionId"}:
            try:
                number = int(item)
            except ValueError as error:
                raise ValueError(f"筛选参数{key}无效") from error
            maximum = 3650 if key == "days" else 2_147_483_647
            if number < 1 or number > maximum:
                raise ValueError(f"筛选参数{key}无效")
            item = str(number)
        normalized.append((key, item))
    return urlencode(normalized)


def serialize_view(record: SavedView) -> SavedViewResponse:
    return SavedViewResponse(
        id=record.id,
        name=record.name,
        query=record.query_string,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("", response_model=list[SavedViewResponse])
def list_saved_views(db: Session = Depends(get_db)) -> list[SavedViewResponse]:
    records = db.scalars(select(SavedView).order_by(SavedView.updated_at.desc(), SavedView.id.desc())).all()
    return [serialize_view(record) for record in records]


def _persist_view(record: SavedView, payload: SavedViewPayload, db: Session) -> SavedViewResponse:
    name = payload.name.strip()
    try:
        query = normalize_saved_query(payload.query)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    record.name = name
    record.query_string = query
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已存在同名视图") from None
    db.refresh(record)
    return serialize_view(record)


@router.post("", response_model=SavedViewResponse, status_code=status.HTTP_201_CREATED)
def create_saved_view(payload: SavedViewPayload, db: Session = Depends(get_db)) -> SavedViewResponse:
    return _persist_view(SavedView(), payload, db)


@router.put("/{view_id}", response_model=SavedViewResponse)
def update_saved_view(
    view_id: int,
    payload: SavedViewPayload,
    db: Session = Depends(get_db),
) -> SavedViewResponse:
    record = db.get(SavedView, view_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="保存视图不存在")
    return _persist_view(record, payload, db)


@router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_view(view_id: int, db: Session = Depends(get_db)) -> Response:
    record = db.get(SavedView, view_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="保存视图不存在")
    db.delete(record)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
