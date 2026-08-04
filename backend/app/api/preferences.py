from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import HermesPreference
from app.schemas import PreferencePage, PreferencePayload, PreferenceResponse
from app.services.preferences import PreferenceNotFound, PreferenceService


router = APIRouter(prefix="/api/preferences", tags=["preferences"])


def serialize_preference(record: HermesPreference) -> PreferenceResponse:
    return PreferenceResponse(
        id=record.id,
        scope=record.scope,
        effect=record.effect,
        value=record.value,
        kind=record.kind,
        note=record.note,
        active=record.active,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("", response_model=PreferencePage)
def list_preferences(db: Session = Depends(get_db)) -> PreferencePage:
    return PreferencePage(
        items=[serialize_preference(record) for record in PreferenceService(db).list()]
    )


@router.post("", response_model=PreferenceResponse, status_code=status.HTTP_201_CREATED)
def save_preference(
    payload: PreferencePayload,
    db: Session = Depends(get_db),
) -> PreferenceResponse:
    record, _ = PreferenceService(db).save(
        scope=payload.scope,
        effect=payload.effect,
        value=payload.value,
        kind=payload.kind,
        note=payload.note,
    )
    return serialize_preference(record)


@router.delete("/{preference_id}", response_model=PreferenceResponse)
def remove_preference(
    preference_id: int,
    db: Session = Depends(get_db),
) -> PreferenceResponse:
    try:
        return serialize_preference(PreferenceService(db).remove(preference_id))
    except PreferenceNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
