from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.data_export import ALL_SECTIONS, DataExportService, ExportFilters, ExportSection

router = APIRouter(prefix="/api/export", tags=["export"])


def remove_file(path: Path) -> None:
    path.unlink(missing_ok=True)


@router.get("")
def export_data(
    background_tasks: BackgroundTasks,
    format: Literal["json", "markdown"] = "json",
    from_date: date | None = Query(default=None, alias="fromDate"),
    to_date: date | None = Query(default=None, alias="toDate"),
    topic_id: int | None = Query(default=None, alias="topicId", gt=0),
    kind: Literal["news", "paper", "job"] | None = None,
    include: list[ExportSection] = Query(default=[]),
    db: Session = Depends(get_db),
) -> FileResponse:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
    sections = tuple(dict.fromkeys(include or ALL_SECTIONS))
    try:
        path, _ = DataExportService(db, ExportFilters(
            from_date=from_date,
            to_date=to_date,
            topic_id=topic_id,
            kind=kind,
            sections=sections,
        )).build(format)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    background_tasks.add_task(remove_file, path)
    extension = "json" if format == "json" else "md"
    media_type = "application/json" if format == "json" else "text/markdown"
    filename = f"zhiliu-export-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.{extension}"
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        background=background_tasks,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
