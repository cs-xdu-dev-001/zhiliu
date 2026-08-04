import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IntelligenceItem, ItemRevision
from app.services.run_service import item_fingerprint


class ItemMaintenanceNotFound(LookupError):
    pass


class ItemMaintenanceConflict(ValueError):
    pass


def item_snapshot(record: IntelligenceItem) -> dict[str, object]:
    return {
        "title": record.title,
        "summary": record.summary,
        "kind": record.kind,
        "importance": record.importance,
        "isIgnored": record.is_ignored,
        "isInvalid": record.is_invalid,
        "mergedIntoId": record.merged_into_id,
    }


def add_revision(
    db: Session,
    record: IntelligenceItem,
    action: str,
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    db.add(
        ItemRevision(
            item_id=record.id,
            action=action,
            before_json=json.dumps(before, ensure_ascii=False, sort_keys=True),
            after_json=json.dumps(after, ensure_ascii=False, sort_keys=True),
        )
    )


class ItemMaintenanceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def apply_feedback(
        self,
        item_id: int,
        *,
        title: str | None = None,
        summary: str | None = None,
        kind: str | None = None,
        priority: str | None = None,
        ignored: bool | None = None,
    ) -> IntelligenceItem:
        record = self.db.get(IntelligenceItem, item_id)
        if record is None:
            raise ItemMaintenanceNotFound("情报不存在")
        if record.merged_into_id is not None:
            raise ItemMaintenanceConflict("该情报已合并，请修改保留项")

        next_title = title or record.title
        if next_title != record.title:
            next_fingerprint = item_fingerprint(next_title, record.url)
            conflict = self.db.scalar(
                select(IntelligenceItem.id).where(
                    IntelligenceItem.fingerprint == next_fingerprint,
                    IntelligenceItem.id != record.id,
                    IntelligenceItem.is_invalid.is_(False),
                    IntelligenceItem.merged_into_id.is_(None),
                )
            )
            if conflict is not None:
                raise ItemMaintenanceConflict("已存在标题和来源相同的情报，请使用合并功能")
        else:
            next_fingerprint = record.fingerprint

        before = item_snapshot(record)
        record.title = next_title
        record.summary = summary or record.summary
        record.kind = kind or record.kind
        record.fingerprint = next_fingerprint
        if priority == "lower":
            record.importance = min(record.importance, 0.3)
        elif priority == "normal":
            record.importance = 0.6
        elif priority == "higher":
            record.importance = max(record.importance, 0.8)
        if ignored is not None:
            record.is_ignored = ignored
        after = item_snapshot(record)
        if before != after:
            add_revision(self.db, record, "hermes_feedback", before, after)
        self.db.commit()
        self.db.refresh(record)
        return record
