import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.mcp_server.schemas import (
    MonitorPayload,
    MonitorReceipt,
    PublishPayload,
    PublishReceipt,
    TaskFailurePayload,
    TaskFeedbackReceipt,
    TaskStartPayload,
)
from app.models import (
    Briefing,
    HermesPublication,
    IntelligenceItem,
    PublicationItem,
    Subscription,
    TaskRun,
)
from app.services.run_service import canonical_item, item_fingerprint, normalize_url
from app.services.preferences import PreferenceService
from app.services.quality import record_quality_decisions


AUTO_CATEGORIES = {
    "news": "微信整理·情报",
    "paper": "微信整理·论文",
    "job": "微信整理·岗位",
}
AUTO_SUBSCRIPTION_IDS = {"news": -1, "paper": -2, "job": -3}
AUTO_SCHEDULE = "0 0 1 1 *"
AUTO_PROMPT = "系统分类：保存Hermes微信一次性整理结果，不参与定时执行。"


def elapsed_ms(started_at: datetime, finished_at: datetime) -> int:
    if started_at.tzinfo is None and finished_at.tzinfo is not None:
        finished_at = finished_at.replace(tzinfo=None)
    elif started_at.tzinfo is not None and finished_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=None)
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


class PublicationConflict(ValueError):
    pass


class PublicationFailure(RuntimeError):
    pass


class MonitorFailure(RuntimeError):
    pass


class TaskFeedbackService:
    def __init__(self, db: Session, *, public_base_url: str = "") -> None:
        self.db = db
        self.public_base_url = public_base_url.rstrip("/")

    def begin(self, payload: TaskStartPayload) -> TaskFeedbackReceipt:
        existing = self.db.scalar(
            select(TaskRun).where(TaskRun.trace_id == payload.trace_id)
        )
        if existing is not None:
            if (
                existing.topic != payload.topic
                or existing.request_summary != payload.request_summary
                or existing.subscription.kind != payload.kind
            ):
                raise PublicationConflict("追踪号已用于不同任务，请生成新追踪号")
            return self._receipt(existing, duplicate=True)

        category = PublicationService(
            self.db,
            public_base_url=self.public_base_url,
        )._get_or_create_category(payload.kind)
        task = TaskRun(
            subscription_id=category.id,
            hermes_run_id=payload.hermes_run_id,
            trace_id=payload.trace_id,
            origin="weixin-hermes",
            topic=payload.topic,
            request_summary=payload.request_summary,
            status="running",
            stage="processing",
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return self._receipt(task, duplicate=False)

    def fail(self, payload: TaskFailurePayload) -> TaskFeedbackReceipt:
        task = self.db.scalar(
            select(TaskRun).where(TaskRun.trace_id == payload.trace_id)
        )
        if task is None:
            raise PublicationConflict("没有找到对应的知流任务，请先调用zhiliu_begin_task")
        if task.status == "success":
            raise PublicationConflict("任务已完成，不能改为失败")
        if payload.hermes_run_id:
            task.hermes_run_id = payload.hermes_run_id
        task.status = "failed"
        task.stage = "failed"
        task.error_message = payload.error_message
        task.finished_at = datetime.now(timezone.utc)
        task.duration_ms = elapsed_ms(task.started_at, task.finished_at)
        self.db.commit()
        return self._receipt(task, duplicate=False)

    def _receipt(self, task: TaskRun, *, duplicate: bool) -> TaskFeedbackReceipt:
        failed = task.status == "failed"
        completed = task.status == "success"
        return TaskFeedbackReceipt(
            task_run_id=task.id,
            trace_id=task.trace_id or "",
            status="failed" if failed else "success" if completed else "running",
            stage="failed" if failed else "completed" if completed else "processing",
            message=(
                task.error_message or "任务处理失败"
                if failed
                else task.result_summary or "任务已完成"
                if completed
                else "知流已受理，Hermes正在整理"
            ),
            task_url=(
                f"{self.public_base_url}/tasks/{task.id}" if self.public_base_url else None
            ),
            duplicate=duplicate,
        )


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
    def __init__(self, db: Session, *, public_base_url: str = "") -> None:
        self.db = db
        self.public_base_url = public_base_url.rstrip("/")

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

        return self._persist(payload, digest, retry_item_conflict=True)

    def _persist(
        self,
        payload: PublishPayload,
        digest: str,
        *,
        retry_item_conflict: bool,
    ) -> PublishReceipt:
        try:
            subscription = self._get_or_create_category(payload.kind)
            preference_service = PreferenceService(self.db)
            accepted_items = [
                item
                for item in payload.items
                if not preference_service.filters_source(item.source, payload.kind)
            ]
            filtered = len(payload.items) - len(accepted_items)
            resolved_items = self._resolve_items(subscription.id, payload)
            inserted = sum(was_inserted for _, was_inserted in resolved_items)
            skipped = len(resolved_items) - inserted
            briefing = self._insert_briefing(
                subscription.id,
                payload,
                len(resolved_items),
            )
            publication = self._create_receipt(
                subscription.id,
                payload,
                digest,
                inserted,
                skipped,
                filtered,
                briefing.id if briefing else None,
            )
            self.db.add_all(
                PublicationItem(
                    publication_id=publication.id,
                    item_id=item.id,
                    ordinal=ordinal,
                    was_inserted=was_inserted,
                )
                for ordinal, (item, was_inserted) in enumerate(resolved_items)
            )
            record_quality_decisions(
                self.db,
                publication,
                payload.items,
                resolved_items,
                {item.source for item in payload.items if preference_service.filters_source(item.source, payload.kind)},
                payload.kind,
            )
            receipt = self._receipt(publication, duplicate=False)
            self.db.commit()
            return receipt
        except IntegrityError as error:
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
            if retry_item_conflict and self._is_item_fingerprint_conflict(error):
                try:
                    if self._has_existing_item(payload):
                        return self._persist(
                            payload,
                            digest,
                            retry_item_conflict=False,
                        )
                except (PublicationConflict, PublicationFailure):
                    raise
                except Exception:
                    self.db.rollback()
            raise PublicationFailure("发布失败，未写入知流") from None
        except Exception:
            self.db.rollback()
            raise PublicationFailure("发布失败，未写入知流") from None

    def _has_existing_item(self, payload: PublishPayload) -> bool:
        for item in payload.items:
            normalized_url = normalize_url(str(item.url)).rstrip("/")
            fingerprint = item_fingerprint(item.title, normalized_url)
            if self.db.scalar(
                select(IntelligenceItem.id).where(
                    IntelligenceItem.fingerprint == fingerprint
                )
            ) is not None:
                return True
        return False

    @staticmethod
    def _is_item_fingerprint_conflict(error: IntegrityError) -> bool:
        detail = str(error.orig).casefold()
        return (
            "intelligence_items" in detail
            and "fingerprint" in detail
            and ("unique" in detail or "duplicate" in detail)
        )

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

    def _resolve_items(
        self,
        subscription_id: int,
        payload: PublishPayload,
    ) -> list[tuple[IntelligenceItem, bool]]:
        resolved: list[tuple[IntelligenceItem, bool]] = []
        seen_item_ids: set[int] = set()
        preference_service = PreferenceService(self.db)
        items = [
            item
            for item in payload.items
            if not preference_service.filters_source(item.source, payload.kind)
        ]
        for item in items:
            normalized_url = normalize_url(str(item.url)).rstrip("/")
            fingerprint = item_fingerprint(item.title, normalized_url)
            existing = self.db.scalar(
                select(IntelligenceItem).where(IntelligenceItem.fingerprint == fingerprint)
            )
            if existing is not None:
                existing = canonical_item(self.db, existing)
                if existing.id not in seen_item_ids:
                    resolved.append((existing, False))
                    seen_item_ids.add(existing.id)
                continue
            source = (
                item.source
                if item.source.endswith(" · 微信Hermes")
                else f"{item.source} · 微信Hermes"
            )
            record = IntelligenceItem(
                subscription_id=subscription_id,
                kind=payload.kind,
                title=item.title,
                summary=item.summary,
                url=normalized_url,
                source=source,
                published_at=item.published_at,
                keywords_json=json.dumps(item.keywords, ensure_ascii=False),
                reason=item.reason,
                importance=preference_service.adjust_importance(
                    item.source, payload.kind, item.importance
                ),
                fingerprint=fingerprint,
            )
            self.db.add(record)
            self.db.flush()
            resolved.append((record, True))
            seen_item_ids.add(record.id)
        return resolved

    def _insert_briefing(
        self,
        subscription_id: int,
        payload: PublishPayload,
        source_count: int,
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
            item_count=source_count,
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
        filtered: int,
        briefing_id: int | None,
    ) -> HermesPublication:
        task = self.db.scalar(
            select(TaskRun).where(TaskRun.trace_id == payload.trace_id)
        )
        publication = HermesPublication(
            idempotency_key=payload.idempotency_key,
            payload_hash=digest,
            subscription_id=subscription_id,
            briefing_id=briefing_id,
            trace_id=payload.trace_id,
            hermes_run_id=payload.hermes_run_id,
            task_run_id=task.id if task else None,
            item_count=inserted,
            skipped_count=skipped,
            filtered_count=filtered,
            topic=payload.topic,
            request_summary=payload.request_summary,
            origin="weixin-hermes",
        )
        self.db.add(publication)
        self.db.flush()
        if task is not None:
            now = datetime.now(timezone.utc)
            report_title = self.db.get(Briefing, briefing_id).title if briefing_id else None
            summary = f"新增{inserted}条情报，复用{skipped}条"
            if filtered:
                summary += f"，按偏好过滤{filtered}条"
            if report_title:
                summary += f"，生成报告《{report_title}》"
            task.hermes_run_id = payload.hermes_run_id or task.hermes_run_id
            task.status = "success"
            task.stage = "completed"
            task.result_summary = summary
            task.error_message = None
            task.finished_at = now
            task.duration_ms = elapsed_ms(task.started_at, now)
        return publication

    def _receipt(self, publication: HermesPublication, *, duplicate: bool) -> PublishReceipt:
        task = self.db.get(TaskRun, publication.task_run_id) if publication.task_run_id else None
        message = task.result_summary if task and task.result_summary else (
            f"新增{publication.item_count}条情报，复用{publication.skipped_count}条"
            + (f"，按偏好过滤{publication.filtered_count}条" if publication.filtered_count else "")
        )
        trace_path = f"/traces/{publication.id}"
        task_path = f"/tasks/{publication.task_run_id}" if publication.task_run_id else None
        briefing_path = f"/reports/{publication.briefing_id}" if publication.briefing_id else None
        return PublishReceipt(
            receipt_id=publication.id,
            trace_id=publication.trace_id or "",
            item_count=publication.item_count,
            skipped_count=publication.skipped_count,
            filtered_count=publication.filtered_count,
            briefing_id=publication.briefing_id,
            task_run_id=publication.task_run_id,
            message=message,
            trace_url=f"{self.public_base_url}{trace_path}" if self.public_base_url else None,
            task_url=(
                f"{self.public_base_url}{task_path}"
                if self.public_base_url and task_path
                else None
            ),
            briefing_url=(
                f"{self.public_base_url}{briefing_path}"
                if self.public_base_url and briefing_path
                else None
            ),
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
