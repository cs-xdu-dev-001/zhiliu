from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db import get_db
from app.services.data_import import (
    MAX_IMPORT_BYTES,
    ContentImportService,
    ImportConflictError,
    ImportValidationError,
    canonical_payload_hash,
    issue_preview_token,
    parse_import_payload,
    verify_preview_token,
)

router = APIRouter(prefix="/api/import", tags=["import"])


async def read_json_body(request: Request) -> bytes:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(status_code=415, detail="仅接受application/json格式")
    if request.headers.get("content-encoding"):
        raise HTTPException(status_code=415, detail="不接受压缩请求体")
    declared = request.headers.get("content-length")
    if declared:
        try:
            if int(declared) > MAX_IMPORT_BYTES:
                raise HTTPException(status_code=413, detail="文件超过10MiB限制")
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Content-Length无效") from error
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_IMPORT_BYTES:
            raise HTTPException(status_code=413, detail="文件超过10MiB限制")
        chunks.append(chunk)
    return b"".join(chunks)


def validation_http_error(error: ImportValidationError) -> HTTPException:
    detail: dict[str, str] = {"message": str(error)}
    if error.path:
        detail["path"] = error.path
    return HTTPException(status_code=422, detail=detail)


@router.post("/preview")
async def preview_import(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    raw = await read_json_body(request)
    try:
        payload = parse_import_payload(raw)
        payload_hash = canonical_payload_hash(raw)
        preview = ContentImportService(db).preview(payload, payload_hash)
        token, expires_at = issue_preview_token(payload_hash, settings.integration_secret_key)
    except ImportValidationError as error:
        raise validation_http_error(error) from error
    response.headers["Cache-Control"] = "no-store"
    return {**preview, "previewToken": token, "expiresAt": expires_at.isoformat()}


@router.post("/confirm")
async def confirm_import(
    request: Request,
    response: Response,
    report_conflict: Literal["keep", "new_version"] = Query(default="keep", alias="reportConflict"),
    preview_token: str = Header(alias="X-Import-Preview-Token", min_length=20, max_length=1000),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    raw = await read_json_body(request)
    payload_hash = canonical_payload_hash(raw)
    try:
        verify_preview_token(preview_token, payload_hash, settings.integration_secret_key)
        payload = parse_import_payload(raw)
        batch, idempotent = ContentImportService(db).commit(payload, payload_hash, report_conflict)
    except ImportValidationError as error:
        raise validation_http_error(error) from error
    except ImportConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    response.headers["Cache-Control"] = "no-store"
    return {"batch": batch, "idempotent": idempotent}


@router.get("/batches")
def list_import_batches(
    response: Response,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return {"items": ContentImportService(db).list_batches(limit)}


@router.post("/batches/{batch_id}/undo")
def undo_import_batch(
    batch_id: int,
    response: Response,
    action_header: Literal["undo-import"] = Header(alias="X-Zhiliu-Action"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        batch = ContentImportService(db).undo(batch_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ImportConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    response.headers["Cache-Control"] = "no-store"
    return {"batch": batch}
