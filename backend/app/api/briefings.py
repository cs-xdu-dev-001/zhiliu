import json
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.db import get_db
from app.models import Briefing, HermesPublication, IntelligenceItem, PublicationItem, TaskRun
from app.api.runs import serialize_task_run
from app.schemas import (
    BriefingDetailResponse,
    BriefingGenerationRequest,
    BriefingPage,
    BriefingRegenerationRequest,
    BriefingResponse,
    BriefingVersionSummaryResponse,
    PublicationSummaryResponse,
    SourceItemResponse,
    TaskRunResponse,
)
from app.services.report_service import build_version_diff, citation_numbers, source_evidence_status
from app.services.run_service import canonical_item

router = APIRouter(prefix="/api/briefings", tags=["briefings"])


def _briefing_source_ids(db: Session, briefing_id: int) -> list[int]:
    publication_id = db.scalar(
        select(HermesPublication.id)
        .where(HermesPublication.briefing_id == briefing_id)
        .order_by(HermesPublication.created_at, HermesPublication.id)
        .limit(1)
    )
    if publication_id is None:
        return []
    return list(db.scalars(
        select(PublicationItem.item_id)
        .where(PublicationItem.publication_id == publication_id)
        .order_by(PublicationItem.ordinal)
    ).all())


def _briefing_instruction(db: Session, briefing_id: int) -> str:
    return db.scalar(
        select(HermesPublication.request_summary)
        .where(HermesPublication.briefing_id == briefing_id)
        .order_by(HermesPublication.created_at, HermesPublication.id)
        .limit(1)
    ) or ""


def _queue_report(
    db: Session,
    *,
    item_ids: list[int],
    instruction: str,
    request_id: str,
    series_id: str,
    version_number: int,
    changes_only: bool = False,
) -> TaskRunResponse:
    expected_instruction = instruction.strip() or "根据所选情报生成专题报告"
    items: list[IntelligenceItem] = []
    seen: set[int] = set()
    for item_id in item_ids:
        item = db.get(IntelligenceItem, item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"情报{item_id}不存在")
        item = canonical_item(db, item)
        if item.id not in seen:
            items.append(item)
            seen.add(item.id)
    if changes_only:
        items = [item for item in items if item.latest_change_type not in (None, "duplicate_message")]
        expected_instruction = f"仅总结相较历史记录的新变化；不要重复无变化背景。{expected_instruction}"
    if not items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="没有可用于生成报告的情报")
    expected_ids = json.dumps([item.id for item in items])
    existing = db.scalar(select(TaskRun).where(TaskRun.trace_id == request_id))
    if existing is not None:
        if (
            existing.origin != "web-report"
            or existing.report_item_ids_json != expected_ids
            or existing.request_summary != expected_instruction
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="requestId已用于另一项任务",
            )
        return serialize_task_run(db, existing)
    for item in items:
        if item.is_invalid:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"情报{item.id}已标记无效")

    task = TaskRun(
        subscription_id=items[0].subscription_id,
        trace_id=request_id,
        origin="web-report",
        topic="生成专题报告",
        request_summary=expected_instruction,
        status="queued",
        stage="accepted",
        report_item_ids_json=expected_ids,
        report_series_id=series_id,
        report_version_number=version_number,
    )
    db.add(task)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raced = db.scalar(select(TaskRun).where(TaskRun.trace_id == request_id))
        if (
            raced is not None
            and raced.origin == "web-report"
            and raced.report_item_ids_json == expected_ids
            and raced.request_summary == expected_instruction
        ):
            return serialize_task_run(db, raced)
        active_series = db.scalar(
            select(TaskRun).where(
                TaskRun.origin == "web-report",
                TaskRun.report_series_id == series_id,
                TaskRun.status.in_(("queued", "running")),
            )
        )
        if active_series is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该报告已有新版本生成中") from None
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="报告任务与现有数据冲突")
    db.refresh(task)
    return serialize_task_run(db, task)


@router.post("/generate", response_model=TaskRunResponse, status_code=status.HTTP_202_ACCEPTED)
def generate_briefing(
    payload: BriefingGenerationRequest,
    db: Session = Depends(get_db),
) -> TaskRunResponse:
    return _queue_report(
        db,
        item_ids=payload.item_ids,
        instruction=payload.instruction,
        request_id=payload.request_id,
        series_id=str(uuid4()),
        version_number=1,
        changes_only=payload.changes_only,
    )


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
    newer_version = aliased(Briefing)
    filters.append(
        or_(
            Briefing.series_id.is_(None),
            ~select(newer_version.id)
            .where(
                newer_version.series_id == Briefing.series_id,
                newer_version.version_number > Briefing.version_number,
            )
            .exists(),
        )
    )
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
    current_source_ids: list[int] = []
    if publication is not None:
        rows = db.execute(
            select(PublicationItem, IntelligenceItem)
            .join(IntelligenceItem, IntelligenceItem.id == PublicationItem.item_id)
            .where(PublicationItem.publication_id == publication.id)
            .order_by(PublicationItem.ordinal)
        ).all()
        cited_numbers = set(citation_numbers(record.content))
        for link, item in rows:
            citation_number = link.ordinal + 1
            evidence_status, evidence_message = source_evidence_status(
                citation_number=citation_number,
                cited_numbers=cited_numbers,
                url=item.url,
                is_invalid=item.is_invalid,
                source_unavailable=item.source_unavailable,
            )
            source_items.append(SourceItemResponse(
                id=item.id,
                title=item.title,
                summary=item.summary,
                source=item.source,
                url=item.url,
                ordinal=link.ordinal,
                was_inserted=link.was_inserted,
                is_invalid=item.is_invalid,
                source_unavailable=item.source_unavailable,
                is_cited=citation_number in cited_numbers,
                evidence_status=evidence_status,
                evidence_message=evidence_message,
            ))
            current_source_ids.append(item.id)
        publication_response = PublicationSummaryResponse.model_validate(publication)
    versions = [record]
    if record.series_id:
        versions = list(
            db.scalars(
                select(Briefing)
                .where(Briefing.series_id == record.series_id)
                .order_by(Briefing.version_number.desc(), Briefing.id.desc())
            ).all()
        )
    previous = db.get(Briefing, record.previous_version_id) if record.previous_version_id else None
    version_diff = None
    if previous is not None:
        version_diff = build_version_diff(
            previous,
            record,
            _briefing_source_ids(db, previous.id),
            current_source_ids,
            _briefing_instruction(db, previous.id),
            publication.request_summary if publication is not None else "",
        )
        changed_source_ids = [
            *version_diff["added_source_ids"],
            *version_diff["removed_source_ids"],
        ]
        changed_sources = {
            item.id: item.title
            for item in db.scalars(
                select(IntelligenceItem).where(IntelligenceItem.id.in_(changed_source_ids))
            ).all()
        } if changed_source_ids else {}
        version_diff["added_sources"] = [
            {"id": item_id, "title": changed_sources.get(item_id, f"情报#{item_id}")}
            for item_id in version_diff["added_source_ids"]
        ]
        version_diff["removed_sources"] = [
            {"id": item_id, "title": changed_sources.get(item_id, f"情报#{item_id}")}
            for item_id in version_diff["removed_source_ids"]
        ]
    return BriefingDetailResponse(
        **BriefingResponse.model_validate(record).model_dump(),
        source_items=source_items,
        publication=publication_response,
        trace_available=publication is not None,
        versions=[BriefingVersionSummaryResponse.model_validate(version) for version in versions],
        version_diff=version_diff,
    )


@router.post("/{briefing_id}/regenerate", response_model=TaskRunResponse, status_code=status.HTTP_202_ACCEPTED)
def regenerate_briefing(
    briefing_id: int,
    payload: BriefingRegenerationRequest,
    db: Session = Depends(get_db),
) -> TaskRunResponse:
    record = db.get(Briefing, briefing_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    publication = db.scalar(
        select(HermesPublication)
        .where(HermesPublication.briefing_id == briefing_id)
        .order_by(HermesPublication.id.desc())
        .limit(1)
    )
    if publication is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="历史报告缺少来源，无法重新生成")
    item_ids = list(
        db.scalars(
            select(PublicationItem.item_id)
            .where(PublicationItem.publication_id == publication.id)
            .order_by(PublicationItem.ordinal)
        ).all()
    )
    item_ids = list(dict.fromkeys([*item_ids, *payload.item_ids]))
    if len(item_ids) > 20:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="单份报告最多使用20条情报")
    series_id = record.series_id or str(uuid4())
    active = db.scalar(
        select(TaskRun).where(
            TaskRun.origin == "web-report",
            TaskRun.report_series_id == series_id,
            TaskRun.status.in_(("queued", "running")),
        )
    )
    if active is not None:
        expected_instruction = payload.instruction.strip() or "根据所选情报生成专题报告"
        expected_ids = json.dumps(item_ids)
        if (
            active.trace_id == payload.request_id
            and active.report_item_ids_json == expected_ids
            and active.request_summary == expected_instruction
        ):
            return serialize_task_run(db, active)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该报告已有新版本生成中")
    latest_version = db.scalar(
        select(func.max(Briefing.version_number)).where(Briefing.series_id == series_id)
    ) or record.version_number
    if record.series_id is None:
        record.series_id = series_id
        record.version_number = 1
    return _queue_report(
        db,
        item_ids=item_ids,
        instruction=payload.instruction,
        request_id=payload.request_id,
        series_id=series_id,
        version_number=latest_version + 1,
        changes_only=payload.changes_only,
    )

