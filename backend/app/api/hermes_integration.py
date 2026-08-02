from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import CurrentUser
from app.db import get_db
from app.schemas import HermesConnectionResponse, HermesConnectionUpdate
from app.services.hermes_integration import HermesIntegrationService

router = APIRouter(prefix="/api/integrations/hermes", tags=["hermes"])

@router.get("", response_model=HermesConnectionResponse)
async def get_hermes(_: CurrentUser, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return HermesIntegrationService(db, settings).response()

@router.put("", response_model=HermesConnectionResponse)
async def put_hermes(payload: HermesConnectionUpdate, _: CurrentUser, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    try:
        return await HermesIntegrationService(db, settings).save_and_test(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/test", response_model=HermesConnectionResponse)
async def test_hermes(_: CurrentUser, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return await HermesIntegrationService(db, settings).test()
