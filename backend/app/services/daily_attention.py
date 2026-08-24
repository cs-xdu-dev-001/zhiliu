import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models import IntelligenceItem, ItemChange, ItemTopic, PersonalizationSettings, TaskRun, Topic
from app.services.personalization import settings

IMPORTANT_CHANGES = {"important_update", "viewpoint_changed", "information_invalid"}


@dataclass(frozen=True)
class RisingTopic:
    id: int
    name: str
    current_count: int
    previous_count: int


@dataclass(frozen=True)
class DailyAttentionSnapshot:
    day: date
    config: PersonalizationSettings
    items: list[IntelligenceItem]
    reasons: dict[int, list[str]]
    rising_topics: list[RisingTopic]
    important_change_count: int
    source_unavailable_count: int
    pending_change_count: int
    consecutive_failure_count: int
    idempotency_key: str

    @property
    def actionable_count(self) -> int:
        return len(self.items) + len(self.rising_topics) + self.consecutive_failure_count


def build_snapshot(db: Session, *, day: date | None = None) -> DailyAttentionSnapshot:
    config = settings(db)
    local_zone = ZoneInfo("Asia/Shanghai")
    target_day = day or datetime.now(local_zone).date()
    start = datetime.combine(target_day, time.min, local_zone).astimezone(timezone.utc)
    end = datetime.combine(target_day, time.max, local_zone).astimezone(timezone.utc)
    event_at = func.coalesce(IntelligenceItem.published_at, IntelligenceItem.created_at)
    effective_score = func.coalesce(IntelligenceItem.personalized_score, IntelligenceItem.importance)
    threshold = max(config.daily_min_importance, 0.8) if config.daily_important_only else config.daily_min_importance
    valid = (IntelligenceItem.is_invalid.is_(False), IntelligenceItem.merged_into_id.is_(None))
    reasons: dict[int, list[str]] = defaultdict(list)
    followed_topic_ids = list(db.scalars(
        select(Topic.id).where(
            Topic.is_followed.is_(True),
            Topic.is_muted.is_(False),
            Topic.merged_into_id.is_(None),
        ).order_by(Topic.id)
    ).all())

    recent_statement = select(distinct(IntelligenceItem.id)).where(
        *valid,
        event_at >= start,
        event_at <= end,
        effective_score >= threshold,
    )
    if followed_topic_ids:
        recent_statement = recent_statement.join(ItemTopic, ItemTopic.item_id == IntelligenceItem.id).where(
            ItemTopic.topic_id.in_(followed_topic_ids)
        )
    recent_ids = db.scalars(recent_statement).all()
    for item_id in recent_ids:
        reasons[item_id].append("高价值新增")

    important_rows = db.execute(
        select(ItemChange.item_id, ItemChange.change_type).join(IntelligenceItem, IntelligenceItem.id == ItemChange.item_id).where(
            *valid,
            ItemChange.detected_at >= start,
            ItemChange.detected_at <= end,
            ItemChange.status != "unlinked",
            ItemChange.change_type.in_(IMPORTANT_CHANGES),
        )
    ).all()
    for item_id, change_type in important_rows:
        reasons[item_id].append("来源失效" if change_type == "information_invalid" else "重要变化")

    unavailable_ids = db.scalars(select(IntelligenceItem.id).where(*valid, IntelligenceItem.source_unavailable.is_(True))).all()
    for item_id in unavailable_ids:
        reasons[item_id].append("来源失效")

    pending_ids = db.scalars(
        select(ItemChange.item_id).join(IntelligenceItem, IntelligenceItem.id == ItemChange.item_id).where(
            *valid,
            ItemChange.status == "pending",
        )
    ).all()
    for item_id in pending_ids:
        reasons[item_id].append("待确认关联")

    rising_topics = _rising_topics(db)
    rising_topic_ids = [topic.id for topic in rising_topics]
    if rising_topic_ids:
        rising_item_ids = db.scalars(
            select(distinct(ItemTopic.item_id)).join(IntelligenceItem, IntelligenceItem.id == ItemTopic.item_id).where(
                ItemTopic.topic_id.in_(rising_topic_ids),
                *valid,
                event_at >= start,
                event_at <= end,
                effective_score >= config.daily_min_importance,
            )
        ).all()
        for item_id in rising_item_ids:
            reasons[item_id].append("关注主题升温")

    candidate_ids = list(reasons)
    items = list(db.scalars(
        select(IntelligenceItem).where(IntelligenceItem.id.in_(candidate_ids)).order_by(
            effective_score.desc(), IntelligenceItem.created_at.desc(), IntelligenceItem.id.desc()
        ).limit(20)
    ).all()) if candidate_ids else []
    selected_ids = {item.id for item in items}
    selected_reasons = {item_id: list(dict.fromkeys(values)) for item_id, values in reasons.items() if item_id in selected_ids}
    scope = f"{target_day.isoformat()}|{config.daily_min_importance:.2f}|{int(config.daily_important_only)}|{','.join(map(str, followed_topic_ids))}"
    digest = hashlib.sha256(scope.encode()).hexdigest()[:24]
    return DailyAttentionSnapshot(
        day=target_day,
        config=config,
        items=items,
        reasons=selected_reasons,
        rising_topics=rising_topics,
        important_change_count=sum(change_type != "information_invalid" for _, change_type in important_rows),
        source_unavailable_count=len(set(unavailable_ids) | {item_id for item_id, change_type in important_rows if change_type == "information_invalid"}),
        pending_change_count=len(set(pending_ids)),
        consecutive_failure_count=_consecutive_failure_count(db),
        idempotency_key=f"daily-attention:{target_day:%Y%m%d}:{digest}",
    )


def build_instruction(snapshot: DailyAttentionSnapshot) -> str:
    reason_lines = [
        f"情报#{item.id}：{'、'.join(snapshot.reasons[item.id])}"
        for item in snapshot.items
    ]
    return (
        f"生成{snapshot.day.isoformat()}每日关注摘要。控制在6条以内、600字以内，结论先行；"
        "每个事实结论必须使用[n]引用对应来源，不得补充资料外事实。"
        f"候选依据：{'；'.join(reason_lines)}。"
        f"另有连续失败任务{snapshot.consecutive_failure_count}个；没有可引用情报时只在任务中心提醒，不写入报告结论。"
    )[:1000]


def _rising_topics(db: Session) -> list[RisingTopic]:
    now = datetime.now(timezone.utc)
    event_at = func.coalesce(IntelligenceItem.published_at, IntelligenceItem.created_at)
    rows = db.execute(
        select(
            Topic.id,
            Topic.name,
            func.count(distinct(ItemTopic.item_id)).filter(event_at >= now - timedelta(days=7)),
            func.count(distinct(ItemTopic.item_id)).filter(event_at >= now - timedelta(days=14), event_at < now - timedelta(days=7)),
        ).select_from(Topic).join(ItemTopic, ItemTopic.topic_id == Topic.id).join(IntelligenceItem, IntelligenceItem.id == ItemTopic.item_id).where(
            Topic.is_followed.is_(True),
            Topic.is_muted.is_(False),
            Topic.merged_into_id.is_(None),
            IntelligenceItem.is_invalid.is_(False),
            IntelligenceItem.merged_into_id.is_(None),
        ).group_by(Topic.id, Topic.name)
    ).all()
    return [RisingTopic(int(topic_id), name, int(current or 0), int(previous or 0)) for topic_id, name, current, previous in rows if int(current or 0) >= max(2, int(previous or 0) + 1)]


def _consecutive_failure_count(db: Session) -> int:
    ranked = select(
        TaskRun.subscription_id,
        TaskRun.status,
        func.row_number().over(partition_by=TaskRun.subscription_id, order_by=(TaskRun.started_at.desc(), TaskRun.id.desc())).label("position"),
    ).subquery()
    rows = db.execute(select(ranked.c.subscription_id, ranked.c.status).where(ranked.c.position <= 3).order_by(ranked.c.subscription_id, ranked.c.position)).all()
    grouped: dict[int, list[str]] = defaultdict(list)
    for subscription_id, status in rows:
        grouped[subscription_id].append(status)
    return sum(len(statuses) >= 2 and statuses[0] == statuses[1] == "failed" for statuses in grouped.values())
