import hashlib
import json
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.api.runs import serialize_task_run
from app.models import (
    Briefing,
    HermesPublication,
    IntelligenceItem,
    ItemBulkOperation,
    ItemRevision,
    ItemTag,
    PublicationItem,
    Subscription,
    TaskRun,
)
from app.schemas import (
    BriefingResponse,
    DashboardResponse,
    IntelligenceItemResponse,
    ItemBulkSkip,
    ItemBulkUpdate,
    ItemBulkUpdateResponse,
    ItemContentUpdate,
    ItemDetailResponse,
    ItemMergeRequest,
    ItemPage,
    ItemRevisionResponse,
    ItemStateUpdate,
    ItemTagsUpdate,
    ItemSourceAvailabilityUpdate,
    ItemValidityUpdate,
    MergeCandidateResponse,
    MergedItemResponse,
    MergeResultResponse,
    PublicationRecordResponse,
)
from app.services.run_service import item_fingerprint
from app.services.item_maintenance import add_revision, item_snapshot
from app.services.quality import LOW_IMPORTANCE_THRESHOLD, STALE_DAYS, stale_item_condition

router = APIRouter(prefix="/api", tags=["intelligence"])

MERGE_CANDIDATE_MIN_SIMILARITY = 0.55


def item_is_stale(record: IntelligenceItem) -> bool:
    threshold = STALE_DAYS.get(record.kind)
    if threshold is None:
        return False
    event_time = record.published_at or record.created_at
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    return event_time < datetime.now(timezone.utc) - timedelta(days=threshold)


def serialize_item(record: IntelligenceItem) -> IntelligenceItemResponse:
    return IntelligenceItemResponse(
        id=record.id,
        subscription_id=record.subscription_id,
        kind=record.kind,
        title=record.title,
        summary=record.summary,
        url=record.url,
        source=record.source,
        published_at=record.published_at,
        keywords=json.loads(record.keywords_json),
        reason=record.reason,
        importance=record.importance,
        is_read=record.is_read,
        is_saved=record.is_saved,
        is_ignored=record.is_ignored,
        is_invalid=record.is_invalid,
        is_stale=item_is_stale(record),
        source_unavailable=record.source_unavailable,
        merged_into_id=record.merged_into_id,
        tags=sorted(tag.name for tag in record.tags),
        created_at=record.created_at,
    )


@router.get("/items", response_model=ItemPage)
def list_items(
    db: Session = Depends(get_db),
    kind: str | None = None,
    state: list[Literal["unread", "saved", "ignored", "invalid", "stale", "low", "source-unavailable"]] = Query(default=[]),
    subscription_id: int | None = Query(default=None, alias="subscriptionId"),
    q: str | None = Query(default=None, max_length=200),
    source: str | None = Query(default=None, max_length=120),
    tag: list[str] = Query(default=[]),
    days: int | None = Query(default=None, ge=1, le=3650),
    sort: Literal["importance", "newest", "oldest", "title"] = "importance",
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ItemPage:
    filters = []
    event_time = func.coalesce(IntelligenceItem.published_at, IntelligenceItem.created_at)
    if kind:
        filters.append(IntelligenceItem.kind == kind)
    if subscription_id:
        filters.append(IntelligenceItem.subscription_id == subscription_id)
    search = (q or "").strip()
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        filters.append(or_(
            IntelligenceItem.title.ilike(pattern, escape="\\"),
            IntelligenceItem.summary.ilike(pattern, escape="\\"),
            IntelligenceItem.source.ilike(pattern, escape="\\"),
            IntelligenceItem.reason.ilike(pattern, escape="\\"),
            IntelligenceItem.keywords_json.ilike(pattern, escape="\\"),
            IntelligenceItem.url.ilike(pattern, escape="\\"),
        ))
    source_filter = (source or "").strip()
    if source_filter:
        filters.append(func.lower(IntelligenceItem.source) == source_filter.casefold())
    if days:
        filters.append(event_time >= datetime.now(timezone.utc) - timedelta(days=days))
    states = set(state)
    tags = list(dict.fromkeys(value.strip() for value in tag if value.strip()))
    if any(len(value) > 40 for value in tags):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="单个标签不能超过40字符")
    for tag_name in tags:
        filters.append(IntelligenceItem.tags.any(ItemTag.name == tag_name))
    if "invalid" in states:
        filters.append(IntelligenceItem.is_invalid.is_(True))
    else:
        filters.extend([
            IntelligenceItem.is_invalid.is_(False),
            IntelligenceItem.merged_into_id.is_(None),
        ])
    if "unread" in states:
        filters.extend([IntelligenceItem.is_read.is_(False), IntelligenceItem.is_ignored.is_(False)])
    if "saved" in states:
        filters.append(IntelligenceItem.is_saved.is_(True))
    if "ignored" in states:
        filters.append(IntelligenceItem.is_ignored.is_(True))
    if "stale" in states:
        filters.append(stale_item_condition())
    if "low" in states:
        filters.append(IntelligenceItem.importance < LOW_IMPORTANCE_THRESHOLD)
    if "source-unavailable" in states:
        filters.append(IntelligenceItem.source_unavailable.is_(True))

    total = db.scalar(select(func.count()).select_from(IntelligenceItem).where(*filters)) or 0
    order_by = {
        "importance": (IntelligenceItem.importance.desc(), IntelligenceItem.created_at.desc(), IntelligenceItem.id.desc()),
        "newest": (event_time.desc(), IntelligenceItem.id.desc()),
        "oldest": (event_time.asc(), IntelligenceItem.id.asc()),
        "title": (func.lower(IntelligenceItem.title).asc(), IntelligenceItem.id.asc()),
    }[sort]
    records = db.scalars(
        select(IntelligenceItem)
        .options(selectinload(IntelligenceItem.tags))
        .where(*filters)
        .order_by(*order_by)
        .limit(limit)
        .offset(offset)
    ).all()
    return ItemPage(items=[serialize_item(record) for record in records], total=total, limit=limit, offset=offset)


@router.get("/items/sources", response_model=list[str])
def list_item_sources(db: Session = Depends(get_db)) -> list[str]:
    return list(db.scalars(
        select(IntelligenceItem.source)
        .where(
            IntelligenceItem.merged_into_id.is_(None),
            IntelligenceItem.source != "",
        )
        .distinct()
        .order_by(func.lower(IntelligenceItem.source))
    ).all())


@router.post("/items/bulk", response_model=ItemBulkUpdateResponse)
def bulk_update_items(payload: ItemBulkUpdate, db: Session = Depends(get_db)) -> ItemBulkUpdateResponse:
    request_body = {
        "ids": sorted(payload.ids),
        "action": payload.action,
        "tags": sorted(payload.tags),
    }
    request_hash = hashlib.sha256(
        json.dumps(request_body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    existing = db.scalar(
        select(ItemBulkOperation).where(ItemBulkOperation.idempotency_key == payload.idempotency_key)
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="幂等键已用于不同的批量操作")
        saved = ItemBulkUpdateResponse.model_validate_json(existing.result_json)
        return saved.model_copy(update={"duplicate": True})

    operation = ItemBulkOperation(
        idempotency_key=payload.idempotency_key,
        request_hash=request_hash,
        result_json="{}",
    )
    db.add(operation)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raced = db.scalar(
            select(ItemBulkOperation).where(ItemBulkOperation.idempotency_key == payload.idempotency_key)
        )
        if raced is not None and raced.request_hash == request_hash:
            saved = ItemBulkUpdateResponse.model_validate_json(raced.result_json)
            return saved.model_copy(update={"duplicate": True})
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="批量操作冲突，请使用新幂等键") from None

    records = db.scalars(
        select(IntelligenceItem)
        .options(selectinload(IntelligenceItem.tags))
        .where(IntelligenceItem.id.in_(payload.ids))
    ).all()
    by_id = {record.id: record for record in records}
    skipped: list[ItemBulkSkip] = []
    updated_ids: list[int] = []
    state_actions: dict[str, tuple[str, bool]] = {
        "read": ("is_read", True),
        "unread": ("is_read", False),
        "save": ("is_saved", True),
        "unsave": ("is_saved", False),
        "ignore": ("is_ignored", True),
        "unignore": ("is_ignored", False),
    }
    for item_id in payload.ids:
        record = by_id.get(item_id)
        if record is None:
            skipped.append(ItemBulkSkip(id=item_id, reason="情报不存在"))
            continue
        if record.merged_into_id is not None:
            skipped.append(ItemBulkSkip(id=item_id, reason="已合并，只读"))
            continue
        before = item_snapshot(record)
        if payload.action in state_actions:
            field, value = state_actions[payload.action]
            if getattr(record, field) == value:
                skipped.append(ItemBulkSkip(id=item_id, reason="无需修改"))
                continue
            setattr(record, field, value)
        elif payload.action in {"invalidate", "restore"}:
            value = payload.action == "invalidate"
            if record.is_invalid == value:
                skipped.append(ItemBulkSkip(id=item_id, reason="无需修改"))
                continue
            record.is_invalid = value
        else:
            current = {tag.name for tag in record.tags}
            if payload.action == "tag":
                additions = [name for name in payload.tags if name not in current]
                if not additions:
                    skipped.append(ItemBulkSkip(id=item_id, reason="无需修改"))
                    continue
                record.tags.extend(ItemTag(name=name) for name in additions)
            else:
                removals = {name for name in payload.tags if name in current}
                if not removals:
                    skipped.append(ItemBulkSkip(id=item_id, reason="无需修改"))
                    continue
                record.tags[:] = [tag_record for tag_record in record.tags if tag_record.name not in removals]
        after = item_snapshot(record)
        action = {
            "invalidate": "invalidated",
            "restore": "restored",
            "tag": "tagged",
            "untag": "untagged",
        }.get(payload.action, f"bulk_{payload.action}")
        add_revision(db, record, action, before, after)
        updated_ids.append(item_id)

    response = ItemBulkUpdateResponse(
        operation_id=operation.id,
        requested=len(payload.ids),
        updated=len(updated_ids),
        updated_ids=updated_ids,
        skipped=skipped,
    )
    operation.result_json = response.model_dump_json(by_alias=False)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raced = db.scalar(
            select(ItemBulkOperation).where(ItemBulkOperation.idempotency_key == payload.idempotency_key)
        )
        if raced is not None and raced.request_hash == request_hash:
            saved = ItemBulkUpdateResponse.model_validate_json(raced.result_json)
            return saved.model_copy(update={"duplicate": True})
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="批量操作冲突，请重试") from None
    return response


@router.put("/items/{item_id}/tags", response_model=IntelligenceItemResponse)
def replace_item_tags(
    item_id: int,
    payload: ItemTagsUpdate,
    db: Session = Depends(get_db),
) -> IntelligenceItemResponse:
    record = db.scalar(
        select(IntelligenceItem)
        .options(selectinload(IntelligenceItem.tags))
        .where(IntelligenceItem.id == item_id)
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="情报不存在")
    if record.merged_into_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已合并情报仅保留审计，不能修改标签")
    before = item_snapshot(record)
    current = {tag.name for tag in record.tags}
    desired = set(payload.tags)
    if current != desired:
        record.tags[:] = [tag_record for tag_record in record.tags if tag_record.name in desired]
        record.tags.extend(ItemTag(name=name) for name in payload.tags if name not in current)
        add_revision(db, record, "tags_replaced", before, item_snapshot(record))
        db.commit()
        db.refresh(record)
    return serialize_item(record)


@router.get("/tags", response_model=list[str])
def list_tags(db: Session = Depends(get_db)) -> list[str]:
    return list(db.scalars(select(ItemTag.name).distinct().order_by(func.lower(ItemTag.name))).all())


@router.get("/items/{item_id}", response_model=ItemDetailResponse)
def get_item(item_id: int, db: Session = Depends(get_db)) -> ItemDetailResponse:
    record = db.get(IntelligenceItem, item_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="情报不存在")
    rows = db.execute(
        select(PublicationItem, HermesPublication, Briefing)
        .join(HermesPublication, HermesPublication.id == PublicationItem.publication_id)
        .outerjoin(Briefing, Briefing.id == HermesPublication.briefing_id)
        .where(PublicationItem.item_id == item_id)
        .order_by(HermesPublication.created_at, HermesPublication.id)
    ).all()
    publications = [
        PublicationRecordResponse(
            id=publication.id,
            trace_id=publication.trace_id,
            origin=publication.origin,
            request_summary=publication.request_summary,
            created_at=publication.created_at,
            hermes_run_id=publication.hermes_run_id,
            task_run_id=publication.task_run_id,
            was_inserted=link.was_inserted,
            ordinal=link.ordinal,
            briefing_id=briefing.id if briefing else None,
            briefing_title=briefing.title if briefing else None,
        )
        for link, publication, briefing in rows
    ]
    revisions = db.scalars(
        select(ItemRevision)
        .where(ItemRevision.item_id == item_id)
        .order_by(ItemRevision.created_at.desc(), ItemRevision.id.desc())
    ).all()
    merged_into = db.get(IntelligenceItem, record.merged_into_id) if record.merged_into_id else None
    return ItemDetailResponse(
        **serialize_item(record).model_dump(),
        publications=publications,
        trace_available=bool(publications),
        revisions=[
            ItemRevisionResponse(
                id=revision.id,
                action=revision.action,
                before=json.loads(revision.before_json),
                after=json.loads(revision.after_json),
                created_at=revision.created_at,
            )
            for revision in revisions
        ],
        merged_into=MergedItemResponse(id=merged_into.id, title=merged_into.title) if merged_into else None,
    )


@router.patch("/items/{item_id}", response_model=IntelligenceItemResponse)
def update_item_state(
    item_id: int,
    payload: ItemStateUpdate,
    db: Session = Depends(get_db),
) -> IntelligenceItemResponse:
    record = db.get(IntelligenceItem, item_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="情报不存在")
    if record.merged_into_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已合并情报仅保留审计，不能修改状态")
    before = item_snapshot(record)
    for field in ("is_read", "is_saved", "is_ignored"):
        value = getattr(payload, field)
        if value is not None:
            setattr(record, field, value)
    after = item_snapshot(record)
    if before != after:
        add_revision(db, record, "state_updated", before, after)
    db.commit()
    db.refresh(record)
    return serialize_item(record)


@router.patch("/items/{item_id}/content", response_model=IntelligenceItemResponse)
def update_item_content(
    item_id: int,
    payload: ItemContentUpdate,
    db: Session = Depends(get_db),
) -> IntelligenceItemResponse:
    record = db.get(IntelligenceItem, item_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="情报不存在")
    if record.merged_into_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该情报已合并，请编辑保留项")
    next_fingerprint = item_fingerprint(payload.title, record.url)
    conflict = db.scalar(
        select(IntelligenceItem).where(
            IntelligenceItem.fingerprint == next_fingerprint,
            IntelligenceItem.id != record.id,
            IntelligenceItem.is_invalid.is_(False),
            IntelligenceItem.merged_into_id.is_(None),
        )
    )
    if conflict is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="已存在标题和来源相同的情报，请使用合并功能",
        )
    before = item_snapshot(record)
    record.title = payload.title
    record.summary = payload.summary
    record.kind = payload.kind
    record.fingerprint = next_fingerprint
    after = item_snapshot(record)
    if before != after:
        add_revision(db, record, "edited", before, after)
    db.commit()
    db.refresh(record)
    return serialize_item(record)


@router.put("/items/{item_id}/validity", response_model=IntelligenceItemResponse)
def update_item_validity(
    item_id: int,
    payload: ItemValidityUpdate,
    db: Session = Depends(get_db),
) -> IntelligenceItemResponse:
    record = db.get(IntelligenceItem, item_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="情报不存在")
    if record.merged_into_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已合并情报仅保留审计，不能修改有效性")
    before = item_snapshot(record)
    record.is_invalid = payload.invalid
    after = item_snapshot(record)
    if before != after:
        add_revision(db, record, "invalidated" if payload.invalid else "restored", before, after)
    db.commit()
    db.refresh(record)
    return serialize_item(record)


@router.put("/items/{item_id}/source-availability", response_model=IntelligenceItemResponse)
def update_item_source_availability(
    item_id: int,
    payload: ItemSourceAvailabilityUpdate,
    db: Session = Depends(get_db),
) -> IntelligenceItemResponse:
    record = db.get(IntelligenceItem, item_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="情报不存在")
    if record.merged_into_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已合并情报仅保留审计，不能修改来源状态")
    before = item_snapshot(record)
    record.source_unavailable = payload.unavailable
    after = item_snapshot(record)
    if before != after:
        add_revision(db, record, "source_unavailable" if payload.unavailable else "source_restored", before, after)
    db.commit()
    db.refresh(record)
    return serialize_item(record)


@router.get("/items/{item_id}/merge-candidates", response_model=list[MergeCandidateResponse])
def list_merge_candidates(
    item_id: int,
    db: Session = Depends(get_db),
) -> list[MergeCandidateResponse]:
    record = db.get(IntelligenceItem, item_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="情报不存在")
    candidates = db.scalars(
        select(IntelligenceItem).where(
            IntelligenceItem.id != item_id,
            IntelligenceItem.kind == record.kind,
            IntelligenceItem.is_invalid.is_(False),
            IntelligenceItem.merged_into_id.is_(None),
        ).limit(50)
    ).all()
    ranked = sorted(
        (
            (
                SequenceMatcher(None, record.title.casefold(), candidate.title.casefold()).ratio(),
                candidate,
            )
            for candidate in candidates
        ),
        key=lambda pair: (-pair[0], -pair[1].id),
    )
    return [
        MergeCandidateResponse(
            id=candidate.id,
            title=candidate.title,
            summary=candidate.summary,
            source=candidate.source,
            url=candidate.url,
            similarity=round(similarity, 3),
        )
        for similarity, candidate in ranked[:8]
        if similarity >= MERGE_CANDIDATE_MIN_SIMILARITY
    ]


@router.post("/items/{item_id}/merge", response_model=MergeResultResponse)
def merge_item(
    item_id: int,
    payload: ItemMergeRequest,
    db: Session = Depends(get_db),
) -> MergeResultResponse:
    if item_id == payload.target_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能合并到自身")
    records = db.scalars(
        select(IntelligenceItem)
        .where(IntelligenceItem.id.in_((item_id, payload.target_id)))
        .with_for_update()
    ).all()
    by_id = {record.id: record for record in records}
    source = by_id.get(item_id)
    target = by_id.get(payload.target_id)
    if source is None or target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源情报或目标情报不存在")
    if source.merged_into_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="源情报已经合并")
    if target.is_invalid or target.merged_into_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="目标情报必须是有效的保留项")
    if source.kind != target.kind:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="仅支持合并相同分类的情报")

    source_before = item_snapshot(source)
    target_before = item_snapshot(target)
    links = db.scalars(
        select(PublicationItem).where(PublicationItem.item_id == source.id)
    ).all()
    moved_links = 0
    removed_duplicates = 0
    for link in links:
        target_link = db.scalar(
            select(PublicationItem).where(
                PublicationItem.publication_id == link.publication_id,
                PublicationItem.item_id == target.id,
            )
        )
        if target_link is not None:
            target_link.ordinal = min(target_link.ordinal, link.ordinal)
            target_link.was_inserted = target_link.was_inserted or link.was_inserted
            db.delete(link)
            removed_duplicates += 1
        else:
            link.item_id = target.id
            moved_links += 1

    target.is_saved = target.is_saved or source.is_saved
    target.is_read = target.is_read and source.is_read
    target.is_ignored = target.is_ignored and source.is_ignored
    target_tags = {tag.name for tag in target.tags}
    target.tags.extend(ItemTag(name=tag.name) for tag in source.tags if tag.name not in target_tags)
    source.is_invalid = True
    source.merged_into_id = target.id
    add_revision(db, source, "merged", source_before, item_snapshot(source))
    add_revision(
        db,
        target,
        "merge_target",
        target_before,
        {**item_snapshot(target), "absorbedItemId": source.id},
    )
    db.commit()
    return MergeResultResponse(
        source_id=source.id,
        target_id=target.id,
        moved_links=moved_links,
        removed_duplicates=removed_duplicates,
    )


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(db: Session = Depends(get_db)) -> DashboardResponse:
    unread_count = db.scalar(
        select(func.count()).select_from(IntelligenceItem).where(
            IntelligenceItem.is_read.is_(False),
            IntelligenceItem.is_ignored.is_(False),
            IntelligenceItem.is_invalid.is_(False),
            IntelligenceItem.merged_into_id.is_(None),
        )
    ) or 0
    saved_count = db.scalar(
        select(func.count()).select_from(IntelligenceItem).where(
            IntelligenceItem.is_saved.is_(True),
            IntelligenceItem.is_invalid.is_(False),
            IntelligenceItem.merged_into_id.is_(None),
        )
    ) or 0
    active_subscriptions = db.scalar(
        select(func.count()).select_from(Subscription).where(Subscription.enabled.is_(True))
    ) or 0
    failed_runs = db.scalar(
        select(func.count()).select_from(TaskRun).where(TaskRun.status == "failed")
    ) or 0
    top_items = db.scalars(
        select(IntelligenceItem)
        .where(
            IntelligenceItem.is_read.is_(False),
            IntelligenceItem.is_ignored.is_(False),
            IntelligenceItem.is_invalid.is_(False),
            IntelligenceItem.merged_into_id.is_(None),
        )
        .order_by(IntelligenceItem.importance.desc())
        .limit(3)
    ).all()
    latest = db.scalar(select(Briefing).order_by(Briefing.created_at.desc()).limit(1))
    recent_runs = db.scalars(
        select(TaskRun).order_by(TaskRun.started_at.desc()).limit(5)
    ).all()
    latest_response = BriefingResponse.model_validate(latest) if latest else None
    return DashboardResponse(
        unread_count=unread_count,
        saved_count=saved_count,
        active_subscriptions=active_subscriptions,
        failed_runs=failed_runs,
        top_items=[serialize_item(record) for record in top_items],
        latest_briefing=latest_response,
        recent_runs=[serialize_task_run(db, record) for record in recent_runs],
    )

