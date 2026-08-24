from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import HermesPreference
from app.schemas import PersonalizationRecalculateResponse, PersonalizationSettingsResponse, PersonalizationSettingsUpdate, PreferencePage, PreferencePayload, PreferenceResponse
from app.services.personalization import recalculate, settings
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
    recalculate(db)
    db.commit()
    return serialize_preference(record)


@router.get("/personalization", response_model=PersonalizationSettingsResponse)
def get_personalization(db: Session = Depends(get_db)) -> PersonalizationSettingsResponse:
    record = settings(db)
    db.commit()
    db.refresh(record)
    return PersonalizationSettingsResponse.model_validate(record)


@router.put("/personalization", response_model=PersonalizationSettingsResponse)
def update_personalization(payload: PersonalizationSettingsUpdate, db: Session = Depends(get_db)) -> PersonalizationSettingsResponse:
    record = settings(db)
    record.auto_learning_enabled = payload.auto_learning_enabled
    recalculate(db)
    db.commit()
    db.refresh(record)
    return PersonalizationSettingsResponse.model_validate(record)


@router.post("/personalization/recalculate", response_model=PersonalizationRecalculateResponse)
def recalculate_personalization(db: Session = Depends(get_db)) -> PersonalizationRecalculateResponse:
    count = recalculate(db)
    config = settings(db)
    db.commit()
    return PersonalizationRecalculateResponse(updated_items=count, algorithm_version=config.algorithm_version)


@router.post("/{preference_id}/restore", response_model=PreferenceResponse)
def restore_preference(preference_id: int, db: Session = Depends(get_db)) -> PreferenceResponse:
    try:
        record = PreferenceService(db).restore(preference_id)
        recalculate(db)
        db.commit()
        return serialize_preference(record)
    except PreferenceNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/{preference_id}", response_model=PreferenceResponse)
def remove_preference(preference_id: int, db: Session = Depends(get_db)) -> PreferenceResponse:
    try:
        record = PreferenceService(db).remove(preference_id)
        recalculate(db)
        db.commit()
        return serialize_preference(record)
    except PreferenceNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
