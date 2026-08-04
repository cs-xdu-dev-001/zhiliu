import json
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import HermesPublication, HermesQualityDecision, IntelligenceItem, PublicationItem


def record_quality_decisions(
    db: Session,
    publication: HermesPublication,
    candidates: Iterable[object],
    resolved: list[tuple[IntelligenceItem, bool]],
    filtered_sources: set[str] | None = None,
    kind: str | None = None,
) -> None:
    from app.services.run_service import item_fingerprint, normalize_url

    inserted_by_id = {record.id: inserted for record, inserted in resolved}
    filtered_sources = {value.casefold() for value in (filtered_sources or set())}
    for candidate in candidates:
        source = str(candidate.source)
        normalized_url = normalize_url(str(candidate.url)).rstrip("/")
        fingerprint = item_fingerprint(str(candidate.title), normalized_url)
        item = db.scalar(select(IntelligenceItem).where(IntelligenceItem.fingerprint == fingerprint))
        if source.casefold() in filtered_sources:
            action, code, reason = "filtered", "source_avoid", "命中Hermes来源避开偏好，未写入"
            item_id = None
        elif item is not None and item.id in inserted_by_id:
            action = "inserted" if inserted_by_id[item.id] else "duplicate"
            code = "accepted" if action == "inserted" else "duplicate_fingerprint"
            reason = "通过质量检查并写入" if action == "inserted" else "标题和原始链接指纹已存在，复用已有情报"
            item_id = item.id
        else:
            action, code, reason, item_id = "accepted", "accepted", "通过质量检查", item.id if item else None
        db.add(
            HermesQualityDecision(
                publication_id=publication.id,
                item_id=item_id,
                action=action,
                reason_code=code,
                reason=reason,
                kind=str(getattr(candidate, "kind", None) or kind or "news"),
                title=str(candidate.title),
                summary=str(candidate.summary),
                url=normalized_url,
                source=source,
                keywords_json=json.dumps(getattr(candidate, "keywords", []), ensure_ascii=False),
                importance=float(getattr(candidate, "importance", 0)),
            )
        )


class QualityNotFound(LookupError):
    pass


class QualityRestoreConflict(ValueError):
    pass


def restore_quality_decision(db: Session, decision_id: int) -> HermesQualityDecision:
    from app.services.run_service import item_fingerprint

    decision = db.get(HermesQualityDecision, decision_id)
    if decision is None:
        raise QualityNotFound("质量记录不存在")
    if decision.action != "filtered":
        raise QualityRestoreConflict("只有被过滤的情报可以恢复")
    if decision.restored_at is not None:
        return decision
    existing = db.scalar(
        select(IntelligenceItem).where(
            IntelligenceItem.fingerprint == item_fingerprint(decision.title, decision.url)
        )
    )
    publication = decision.publication
    if existing is None:
        source = decision.source
        if publication.origin == "weixin-hermes" and not source.endswith(" · 微信Hermes"):
            source = f"{source} · 微信Hermes"
        existing = IntelligenceItem(
            subscription_id=publication.subscription_id,
            kind=decision.kind,
            title=decision.title,
            summary=decision.summary,
            url=decision.url,
            source=source,
            keywords_json=decision.keywords_json,
            reason="从质量中心恢复：" + decision.reason,
            importance=decision.importance,
            fingerprint=item_fingerprint(decision.title, decision.url),
        )
        db.add(existing)
        db.flush()
        was_inserted = True
    else:
        was_inserted = False
    linked = db.scalar(
        select(PublicationItem).where(
            PublicationItem.publication_id == publication.id,
            PublicationItem.item_id == existing.id,
        )
    )
    if linked is None:
        ordinal = db.scalar(
            select(func.coalesce(func.max(PublicationItem.ordinal), -1)).where(
                PublicationItem.publication_id == publication.id
            )
        )
        db.add(PublicationItem(publication_id=publication.id, item_id=existing.id, ordinal=ordinal + 1, was_inserted=was_inserted))
        publication.item_count += 1
        publication.filtered_count = max(0, publication.filtered_count - 1)
    decision.item_id = existing.id
    decision.restored_at = datetime.now(timezone.utc)
    decision.reason_code = "restored"
    decision.reason = "用户从质量中心恢复"
    db.commit()
    db.refresh(decision)
    return decision
