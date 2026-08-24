import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IntelligenceItem, ItemChange, ItemRevision

CHANGE_TYPES = {
    "first_appearance", "ongoing", "important_update", "duplicate_message",
    "viewpoint_changed", "information_invalid",
}


@dataclass(frozen=True)
class ChangeInput:
    change_type: str
    related_item_id: int | None = None
    basis: str = ""
    source_urls: tuple[str, ...] = ()


def content_snapshot(item: IntelligenceItem) -> dict[str, Any]:
    return {
        "title": item.title, "summary": item.summary, "kind": item.kind,
        "source": item.source, "url": item.url, "publishedAt": item.published_at.isoformat() if item.published_at else None,
        "keywords": json.loads(item.keywords_json), "reason": item.reason, "importance": item.importance,
    }


def incoming_snapshot(item: Any, *, kind: str, url: str, source: str | None = None, importance: float | None = None) -> dict[str, Any]:
    return {
        "title": item.title, "summary": item.summary, "kind": kind,
        "source": source or item.source, "url": url,
        "publishedAt": item.published_at.isoformat() if item.published_at else None,
        "keywords": list(item.keywords), "reason": item.reason,
        "importance": item.importance if importance is None else importance,
    }


def meaningful_change(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return any(before.get(key) != after.get(key) for key in ("title", "summary", "kind", "publishedAt", "keywords", "reason"))


def apply_snapshot(item: IntelligenceItem, after: dict[str, Any], fingerprint: str) -> None:
    item.title = after["title"]
    item.summary = after["summary"]
    item.kind = after["kind"]
    item.source = after["source"]
    item.url = after["url"]
    item.keywords_json = json.dumps(after["keywords"], ensure_ascii=False)
    item.reason = after["reason"]
    item.importance = after["importance"]
    item.fingerprint = fingerprint


def record_change(
    db: Session, item: IntelligenceItem, change: ChangeInput, *, idempotency_key: str,
    task_run_id: int | None = None, publication_id: int | None = None,
    before: dict[str, Any] | None = None, after: dict[str, Any] | None = None,
) -> ItemChange:
    existing = db.scalar(select(ItemChange).where(ItemChange.idempotency_key == idempotency_key))
    if existing is not None:
        return existing
    related = db.get(IntelligenceItem, change.related_item_id) if change.related_item_id else None
    if change.related_item_id and related is None:
        raise ValueError(f"关联情报{change.related_item_id}不存在")
    needs_relation = change.change_type in {"ongoing", "important_update", "viewpoint_changed"}
    event = ItemChange(
        item_id=item.id, related_item_id=related.id if related else None,
        task_run_id=task_run_id, publication_id=publication_id,
        change_type=change.change_type, basis=change.basis,
        source_urls_json=json.dumps(list(change.source_urls), ensure_ascii=False),
        before_json=json.dumps(before or {}, ensure_ascii=False),
        after_json=json.dumps(after or content_snapshot(item), ensure_ascii=False),
        status="pending" if needs_relation and related is None else "confirmed",
        idempotency_key=idempotency_key,
    )
    db.add(event)
    item.latest_change_type = change.change_type
    db.flush()
    return event


def record_automatic_revision(db: Session, item: IntelligenceItem, before: dict[str, Any], after: dict[str, Any]) -> None:
    db.add(ItemRevision(item_id=item.id, action="source_updated", before_json=json.dumps(before, ensure_ascii=False), after_json=json.dumps(after, ensure_ascii=False)))
