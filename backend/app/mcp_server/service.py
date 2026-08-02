import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.mcp_server.schemas import (
    MonitorPayload,
    MonitorReceipt,
    PublishPayload,
    PublishReceipt,
)
from app.models import Briefing, HermesPublication, IntelligenceItem, Subscription
from app.services.run_service import item_fingerprint, normalize_url


AUTO_CATEGORIES = {
    "news": "微信整理·情报",
    "paper": "微信整理·论文",
    "job": "微信整理·岗位",
}
AUTO_SUBSCRIPTION_IDS = {"news": -1, "paper": -2, "job": -3}
AUTO_SCHEDULE = "0 0 1 1 *"
AUTO_PROMPT = "系统分类：保存Hermes微信一次性整理结果，不参与定时执行。"


class PublicationConflict(ValueError):
    pass


class PublicationFailure(RuntimeError):
    pass


class MonitorFailure(RuntimeError):
    pass


def monitor_subscription_id(payload: MonitorPayload) -> int:
    identity = {
        "name": payload.name,
        "kind": payload.kind,
        "schedule": payload.schedule,
        "prompt": payload.prompt,
    }
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    value = int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big") % (2**62 - 1000)
    return -1000 - value


def publication_hash(payload: PublishPayload) -> str:
    body = payload.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude={"idempotency_key"},
    )
    items = body.get("items", [])
    for item in items:
        item["url"] = normalize_url(item["url"]).rstrip("/")
        item["keywords"] = sorted(item.get("keywords", []), key=str.casefold)
    body["items"] = sorted(
        items,
        key=lambda item: (item["title"].casefold(), item["url"]),
    )
    encoded = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class PublicationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def publish(self, payload: PublishPayload) -> PublishReceipt:
        digest = publication_hash(payload)
        by_key = self.db.scalar(
            select(HermesPublication).where(
                HermesPublication.idempotency_key == payload.idempotency_key
            )
        )
        if by_key is not None:
            if by_key.payload_hash != digest:
                raise PublicationConflict("幂等键已用于不同内容，请生成新键后重试")
            return self._receipt(by_key, duplicate=True)

        by_hash = self.db.scalar(
            select(HermesPublication).where(HermesPublication.payload_hash == digest)
        )
        if by_hash is not None:
            return self._receipt(by_hash, duplicate=True)

        try:
            subscription = self._get_or_create_category(payload.kind)
            inserted, skipped = self._insert_items(subscription.id, payload)
            briefing = self._insert_briefing(subscription.id, payload, inserted)
            publication = self._create_receipt(
                subscription.id,
                payload,
                digest,
                inserted,
                skipped,
                briefing.id if briefing else None,
            )
            receipt = self._receipt(publication, duplicate=False)
            self.db.commit()
            return receipt
        except IntegrityError:
            self.db.rollback()
            by_key = self.db.scalar(
                select(HermesPublication).where(
                    HermesPublication.idempotency_key == payload.idempotency_key
                )
            )
            if by_key is not None:
                if by_key.payload_hash == digest:
                    return self._receipt(by_key, duplicate=True)
                raise PublicationConflict("幂等键已用于不同内容，请生成新键后重试") from None
            by_hash = self.db.scalar(
                select(HermesPublication).where(HermesPublication.payload_hash == digest)
            )
            if by_hash is not None:
                return self._receipt(by_hash, duplicate=True)
            raise PublicationFailure("发布失败，未写入知流") from None
        except Exception:
            self.db.rollback()
            raise PublicationFailure("发布失败，未写入知流") from None

    def _get_or_create_category(self, kind: str) -> Subscription:
        name = AUTO_CATEGORIES[kind]
        subscription_id = AUTO_SUBSCRIPTION_IDS[kind]
        record = self.db.get(Subscription, subscription_id)
        if record is None:
            record = Subscription(
                id=subscription_id,
                name=name,
                kind=kind,
                keywords_json="[]",
                schedule=AUTO_SCHEDULE,
                prompt=AUTO_PROMPT,
                enabled=False,
            )
            self.db.add(record)
            self.db.flush()
        else:
            record.name = name
            record.kind = kind
            record.keywords_json = "[]"
            record.schedule = AUTO_SCHEDULE
            record.prompt = AUTO_PROMPT
            record.enabled = False
        return record

    def _insert_items(self, subscription_id: int, payload: PublishPayload) -> tuple[int, int]:
        inserted = 0
        skipped = 0
        for item in payload.items:
            normalized_url = normalize_url(str(item.url)).rstrip("/")
            fingerprint = item_fingerprint(item.title, normalized_url)
            existing = self.db.scalar(
                select(IntelligenceItem.id).where(IntelligenceItem.fingerprint == fingerprint)
            )
            if existing is not None:
                skipped += 1
                continue
            source = (
                item.source
                if item.source.endswith(" · 微信Hermes")
                else f"{item.source} · 微信Hermes"
            )
            self.db.add(
                IntelligenceItem(
                    subscription_id=subscription_id,
                    kind=payload.kind,
                    title=item.title,
                    summary=item.summary,
                    url=normalized_url,
                    source=source,
                    published_at=item.published_at,
                    keywords_json=json.dumps(item.keywords, ensure_ascii=False),
                    reason=item.reason,
                    importance=item.importance,
                    fingerprint=fingerprint,
                )
            )
            inserted += 1
        return inserted, skipped

    def _insert_briefing(
        self,
        subscription_id: int,
        payload: PublishPayload,
        inserted: int,
    ) -> Briefing | None:
        if payload.briefing is None:
            return None
        prefix = "微信整理 · "
        title = payload.briefing.title
        briefing = Briefing(
            subscription_id=subscription_id,
            title=title if title.startswith(prefix) else f"{prefix}{title}",
            kind=payload.kind,
            content=payload.briefing.content,
            item_count=inserted,
            period_start=payload.briefing.period_start,
            period_end=payload.briefing.period_end,
        )
        self.db.add(briefing)
        self.db.flush()
        return briefing

    def _create_receipt(
        self,
        subscription_id: int,
        payload: PublishPayload,
        digest: str,
        inserted: int,
        skipped: int,
        briefing_id: int | None,
    ) -> HermesPublication:
        publication = HermesPublication(
            idempotency_key=payload.idempotency_key,
            payload_hash=digest,
            subscription_id=subscription_id,
            briefing_id=briefing_id,
            item_count=inserted,
            skipped_count=skipped,
            topic=payload.topic,
            request_summary=payload.request_summary,
            origin="weixin-hermes",
        )
        self.db.add(publication)
        self.db.flush()
        return publication

    @staticmethod
    def _receipt(publication: HermesPublication, *, duplicate: bool) -> PublishReceipt:
        return PublishReceipt(
            receipt_id=publication.id,
            item_count=publication.item_count,
            skipped_count=publication.skipped_count,
            briefing_id=publication.briefing_id,
            created_at=publication.created_at,
            duplicate=duplicate,
        )


class MonitorService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, payload: MonitorPayload) -> MonitorReceipt:
        keywords_json = json.dumps(payload.keywords, ensure_ascii=False)
        subscription_id = monitor_subscription_id(payload)
        try:
            existing = self.db.scalar(
                select(Subscription).where(
                    Subscription.name == payload.name,
                    Subscription.kind == payload.kind,
                    Subscription.schedule == payload.schedule,
                    Subscription.prompt == payload.prompt,
                )
            )
            if existing is not None:
                existing.keywords_json = keywords_json
                existing.enabled = True
                self.db.commit()
                return MonitorReceipt(subscription_id=existing.id, created=False)

            record = Subscription(
                id=subscription_id,
                name=payload.name,
                kind=payload.kind,
                keywords_json=keywords_json,
                schedule=payload.schedule,
                prompt=payload.prompt,
                enabled=True,
            )
            self.db.add(record)
            self.db.flush()
            receipt = MonitorReceipt(subscription_id=record.id, created=True)
            self.db.commit()
            return receipt
        except IntegrityError:
            self.db.rollback()
            try:
                existing = self.db.get(Subscription, subscription_id)
                if existing is not None and self._matches(existing, payload):
                    return MonitorReceipt(subscription_id=existing.id, created=False)
            except Exception:
                self.db.rollback()
            raise MonitorFailure("监测创建失败，未写入知流") from None
        except Exception:
            self.db.rollback()
            raise MonitorFailure("监测创建失败，未写入知流") from None

    @staticmethod
    def _matches(record: Subscription, payload: MonitorPayload) -> bool:
        return (
            record.name == payload.name
            and record.kind == payload.kind
            and record.schedule == payload.schedule
            and record.prompt == payload.prompt
        )
