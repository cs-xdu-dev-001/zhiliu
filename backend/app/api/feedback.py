from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ContentFeedback
from app.schemas import FeedbackCreateRequest, FeedbackPage, FeedbackResponse, FeedbackUpdateRequest, FeedbackVersionRequest
from app.services.feedback import FeedbackConflict, FeedbackNotFound, FeedbackService, FeedbackVersionConflict
from app.services.preferences import PreferenceNotFound

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


def serialize(record: ContentFeedback) -> FeedbackResponse:
    return FeedbackResponse.model_validate(record)


def translate(error: Exception) -> HTTPException:
    if isinstance(error, FeedbackNotFound):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, FeedbackVersionConflict):
        return HTTPException(status_code=409, detail=str(error))
    return HTTPException(status_code=422, detail=str(error))


@router.get("", response_model=FeedbackPage)
def list_feedback(
    item_id: int | None = Query(default=None, alias="itemId", gt=0),
    briefing_id: int | None = Query(default=None, alias="briefingId", gt=0),
    db: Session = Depends(get_db),
) -> FeedbackPage:
    if (item_id is None) == (briefing_id is None):
        raise HTTPException(status_code=422, detail="必须且只能指定itemId或briefingId")
    return FeedbackPage(items=[serialize(record) for record in FeedbackService(db).list(item_id=item_id, briefing_id=briefing_id)])


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def create_feedback(payload: FeedbackCreateRequest, db: Session = Depends(get_db)) -> FeedbackResponse:
    try:
        record, _ = FeedbackService(db).create(
            target_type=payload.target_type,
            target_id=payload.target_id,
            feedback_type=payload.feedback_type,
            note=payload.note,
            idempotency_key=payload.idempotency_key,
            apply_long_term=payload.apply_long_term,
        )
        return serialize(record)
    except (FeedbackConflict, FeedbackNotFound, FeedbackVersionConflict, PreferenceNotFound) as error:
        db.rollback()
        raise translate(error) from error


@router.patch("/{feedback_id}", response_model=FeedbackResponse)
def update_feedback(feedback_id: int, payload: FeedbackUpdateRequest, db: Session = Depends(get_db)) -> FeedbackResponse:
    try:
        return serialize(FeedbackService(db).update(
            feedback_id,
            version=payload.version,
            note=payload.note,
            apply_long_term=payload.apply_long_term,
        ))
    except (FeedbackConflict, FeedbackNotFound, FeedbackVersionConflict, PreferenceNotFound) as error:
        db.rollback()
        raise translate(error) from error


@router.post("/{feedback_id}/revoke", response_model=FeedbackResponse)
def revoke_feedback(feedback_id: int, payload: FeedbackVersionRequest, db: Session = Depends(get_db)) -> FeedbackResponse:
    try:
        return serialize(FeedbackService(db).revoke(feedback_id, version=payload.version))
    except (FeedbackConflict, FeedbackNotFound, FeedbackVersionConflict, PreferenceNotFound) as error:
        db.rollback()
        raise translate(error) from error


@router.post("/{feedback_id}/restore", response_model=FeedbackResponse)
def restore_feedback(feedback_id: int, payload: FeedbackVersionRequest, db: Session = Depends(get_db)) -> FeedbackResponse:
    try:
        return serialize(FeedbackService(db).restore(feedback_id, version=payload.version))
    except (FeedbackConflict, FeedbackNotFound, FeedbackVersionConflict, PreferenceNotFound) as error:
        db.rollback()
        raise translate(error) from error
