import json
import re
import unicodedata

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models import HermesPreference, IntelligenceItem, ItemTopic, Subscription, Topic, TopicAlias


def normalize_topic(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"[\s_\-/·•]+", " ", value).strip(" ,，。.!！?？:：;；")


def ensure_topic(db: Session, name: str, *, source: str = "keyword") -> Topic | None:
    display = unicodedata.normalize("NFKC", name).strip()[:120]
    normalized = normalize_topic(display)
    if not normalized:
        return None
    alias = db.scalar(select(TopicAlias).where(TopicAlias.normalized_name == normalized))
    if alias is not None:
        return alias.topic
    topic = db.scalar(select(Topic).where(Topic.normalized_name == normalized))
    if topic is None:
        topic = Topic(name=display, normalized_name=normalized)
        db.add(topic)
        db.flush()
    db.add(TopicAlias(topic_id=topic.id, name=display, normalized_name=normalized, source=source))
    db.flush()
    return topic


def link_item_topics(db: Session, item: IntelligenceItem) -> None:
    try:
        names = json.loads(item.keywords_json or "[]")
    except (TypeError, json.JSONDecodeError):
        names = []
    candidates = [(str(name), "keyword", 1.0) for name in names]
    subscription = db.get(Subscription, item.subscription_id)
    if subscription is not None:
        subscription_names = [subscription.name]
        try:
            subscription_names.extend(json.loads(subscription.keywords_json or "[]"))
        except (TypeError, json.JSONDecodeError):
            pass
        candidates.extend((str(name), "subscription", 0.8) for name in subscription_names)
    existing = set(db.scalars(select(ItemTopic.topic_id).where(ItemTopic.item_id == item.id)).all())
    for name, source, confidence in candidates:
        if normalize_topic(name) in {"news", "paper", "job"}:
            continue
        topic = ensure_topic(db, name, source=source)
        if topic and topic.id not in existing:
            db.add(ItemTopic(item_id=item.id, topic_id=topic.id, source=source, confidence=confidence))
            existing.add(topic.id)


def reconcile_topics(db: Session) -> None:
    inspector = inspect(db.get_bind())
    tables = set(inspector.get_table_names())
    if not {"topics", "topic_aliases", "item_topics", "intelligence_items"}.issubset(tables):
        return
    item_columns = {column["name"] for column in inspector.get_columns("intelligence_items")}
    if not {"is_invalid", "merged_into_id", "source_unavailable"}.issubset(item_columns):
        return
    items = db.scalars(select(IntelligenceItem)).all()
    for item in items:
        link_item_topics(db, item)
    for subscription in db.scalars(select(Subscription)).all():
        names = [subscription.name]
        try:
            names.extend(json.loads(subscription.keywords_json or "[]"))
        except (TypeError, json.JSONDecodeError):
            pass
        for name in names:
            ensure_topic(db, str(name), source="subscription")
    for preference in db.scalars(select(HermesPreference).where(HermesPreference.scope == "topic", HermesPreference.active.is_(True))).all():
        ensure_topic(db, preference.value, source="preference")
    db.commit()
