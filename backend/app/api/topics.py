from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from app.api.items import serialize_item
from app.api.runs import serialize_task_run
from app.db import get_db
from app.models import Briefing, HermesPublication, IntelligenceItem, ItemTopic, PublicationItem, TaskRun, Topic, TopicAlias
from app.schemas import BriefingResponse, TopicDetail, TopicMergeRequest, TopicPage, TopicStateUpdate, TopicSummary

router = APIRouter(prefix="/api/topics", tags=["topics"])


def _trend(current: int, previous: int) -> str:
    if current >= max(2, previous + 1):
        return "rising"
    if previous >= max(2, current + 1):
        return "falling"
    return "steady"


def _summary(db: Session, topic: Topic) -> TopicSummary:
    now = datetime.now(timezone.utc)
    event_at = func.coalesce(IntelligenceItem.published_at, IntelligenceItem.created_at)
    base = [ItemTopic.topic_id == topic.id, IntelligenceItem.is_invalid.is_(False), IntelligenceItem.merged_into_id.is_(None)]
    counts = db.execute(
        select(
            func.count(distinct(ItemTopic.item_id)).filter(event_at >= now - timedelta(days=7)),
            func.count(distinct(ItemTopic.item_id)).filter(event_at >= now - timedelta(days=30)),
            func.count(distinct(ItemTopic.item_id)).filter(event_at >= now - timedelta(days=14), event_at < now - timedelta(days=7)),
            func.count(distinct(IntelligenceItem.source)),
            func.max(event_at),
        ).select_from(ItemTopic).join(IntelligenceItem, IntelligenceItem.id == ItemTopic.item_id).where(*base)
    ).one()
    current, month, previous, sources, latest = (int(counts[0] or 0), int(counts[1] or 0), int(counts[2] or 0), int(counts[3] or 0), counts[4])
    return TopicSummary(id=topic.id, name=topic.name, description=topic.description, is_followed=topic.is_followed, is_pinned=topic.is_pinned, is_muted=topic.is_muted, item_count_7_days=current, item_count_30_days=month, previous_7_days_count=previous, trend=_trend(current, previous), source_count=sources, latest_at=latest)


def _summaries(db: Session, topics: list[Topic]) -> list[TopicSummary]:
    if not topics:
        return []
    now = datetime.now(timezone.utc)
    event_at = func.coalesce(IntelligenceItem.published_at, IntelligenceItem.created_at)
    valid_item = (IntelligenceItem.is_invalid.is_(False), IntelligenceItem.merged_into_id.is_(None))
    rows = db.execute(
        select(
            ItemTopic.topic_id,
            func.count(distinct(ItemTopic.item_id)).filter(event_at >= now - timedelta(days=7), *valid_item),
            func.count(distinct(ItemTopic.item_id)).filter(event_at >= now - timedelta(days=30), *valid_item),
            func.count(distinct(ItemTopic.item_id)).filter(event_at >= now - timedelta(days=14), event_at < now - timedelta(days=7), *valid_item),
            func.count(distinct(IntelligenceItem.source)).filter(*valid_item),
            func.max(event_at).filter(*valid_item),
        ).select_from(ItemTopic).join(IntelligenceItem, IntelligenceItem.id == ItemTopic.item_id).where(ItemTopic.topic_id.in_([topic.id for topic in topics])).group_by(ItemTopic.topic_id)
    ).all()
    metrics = {row[0]: row[1:] for row in rows}
    result = []
    for topic in topics:
        current, month, previous, sources, latest = metrics.get(topic.id, (0, 0, 0, 0, None))
        result.append(TopicSummary(id=topic.id, name=topic.name, description=topic.description, is_followed=topic.is_followed, is_pinned=topic.is_pinned, is_muted=topic.is_muted, item_count_7_days=int(current or 0), item_count_30_days=int(month or 0), previous_7_days_count=int(previous or 0), trend=_trend(int(current or 0), int(previous or 0)), source_count=int(sources or 0), latest_at=latest))
    return result


@router.get("", response_model=TopicPage)
def list_topics(
    q: str | None = Query(default=None, max_length=120),
    state: Literal["followed", "pinned", "muted"] | None = None,
    sort: Literal["signal", "latest", "name"] = "signal",
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> TopicPage:
    filters = [Topic.merged_into_id.is_(None)]
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        filters.append(or_(Topic.name.ilike(pattern), Topic.aliases.any(TopicAlias.name.ilike(pattern))))
    if state:
        filters.append(getattr(Topic, f"is_{state}").is_(True))
    topics = db.scalars(select(Topic).where(*filters)).all()
    summaries = _summaries(db, list(topics))
    if not q and not state:
        summaries = [row for row in summaries if row.latest_at is not None or row.is_followed or row.is_pinned]
    if sort == "name":
        summaries.sort(key=lambda row: row.name.casefold())
    elif sort == "latest":
        summaries.sort(key=lambda row: row.latest_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    else:
        summaries.sort(key=lambda row: (row.is_pinned, row.is_followed, row.item_count_7_days, row.item_count_30_days), reverse=True)
    return TopicPage(items=summaries[offset:offset + limit], total=len(summaries), limit=limit, offset=offset)


@router.get("/{topic_id}", response_model=TopicDetail)
def get_topic(topic_id: int, db: Session = Depends(get_db)) -> TopicDetail:
    topic = db.get(Topic, topic_id)
    if topic is None or topic.merged_into_id is not None:
        raise HTTPException(status_code=404, detail="主题不存在")
    item_ids = select(ItemTopic.item_id).where(ItemTopic.topic_id == topic.id)
    items = db.scalars(select(IntelligenceItem).where(IntelligenceItem.id.in_(item_ids), IntelligenceItem.is_invalid.is_(False), IntelligenceItem.merged_into_id.is_(None)).order_by(IntelligenceItem.importance.desc(), IntelligenceItem.created_at.desc()).limit(20)).all()
    publication_ids = select(PublicationItem.publication_id).where(PublicationItem.item_id.in_(item_ids))
    briefings = db.scalars(select(Briefing).join(HermesPublication, HermesPublication.briefing_id == Briefing.id).where(HermesPublication.id.in_(publication_ids)).distinct().order_by(Briefing.created_at.desc()).limit(8)).all()
    runs = db.scalars(select(TaskRun).where(or_(TaskRun.topic.ilike(f"%{topic.name}%"), TaskRun.id.in_(select(HermesPublication.task_run_id).where(HermesPublication.id.in_(publication_ids))))).order_by(TaskRun.started_at.desc()).limit(8)).all()
    return TopicDetail(**_summary(db, topic).model_dump(), aliases=[alias.name for alias in topic.aliases], latest_items=[serialize_item(item) for item in items], related_briefings=[BriefingResponse.model_validate(row) for row in briefings], related_runs=[serialize_task_run(db, row) for row in runs])


@router.patch("/{topic_id}", response_model=TopicSummary)
def update_topic(topic_id: int, payload: TopicStateUpdate, db: Session = Depends(get_db)) -> TopicSummary:
    topic = db.get(Topic, topic_id)
    if topic is None or topic.merged_into_id is not None:
        raise HTTPException(status_code=404, detail="主题不存在")
    for field in ("is_followed", "is_pinned", "is_muted"):
        value = getattr(payload, field)
        if value is not None:
            setattr(topic, field, value)
    db.commit(); db.refresh(topic)
    return _summary(db, topic)


@router.post("/{topic_id}/merge", response_model=TopicSummary)
def merge_topic(topic_id: int, payload: TopicMergeRequest, db: Session = Depends(get_db)) -> TopicSummary:
    if topic_id == payload.target_id:
        raise HTTPException(status_code=400, detail="不能合并到自身")
    source, target = db.get(Topic, topic_id), db.get(Topic, payload.target_id)
    if source is None or target is None or source.merged_into_id is not None or target.merged_into_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="源主题或目标主题不可合并")
    target_item_ids = set(db.scalars(select(ItemTopic.item_id).where(ItemTopic.topic_id == target.id)).all())
    for link in list(source.item_links):
        if link.item_id in target_item_ids:
            db.delete(link)
        else:
            link.topic_id = target.id
    for alias in list(source.aliases):
        alias.topic_id = target.id
    target.is_followed = target.is_followed or source.is_followed
    target.is_pinned = target.is_pinned or source.is_pinned
    target.is_muted = target.is_muted and source.is_muted
    source.merged_into_id = target.id
    db.commit(); db.refresh(target)
    return _summary(db, target)
