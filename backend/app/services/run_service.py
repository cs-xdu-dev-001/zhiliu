import hashlib
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Briefing, HermesPublication, IntelligenceItem, PublicationItem, TaskRun
from app.services.hermes import HermesClient, HermesTimeout, HermesUnavailable
from app.services.quality import record_quality_decisions


def normalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def item_fingerprint(title: str, url: str) -> str:
    normalized_title = " ".join(title.casefold().split())
    normalized_url = normalize_url(url).rstrip("/")
    return hashlib.sha256(f"{normalized_title}\n{normalized_url}".encode()).hexdigest()


def canonical_item(db: Session, item: IntelligenceItem) -> IntelligenceItem:
    """Follow a soft-merge chain so every future citation reaches the retained item."""
    seen = {item.id}
    current = item
    while current.merged_into_id is not None:
        if current.merged_into_id in seen:
            raise RuntimeError("情报合并关系存在循环")
        seen.add(current.merged_into_id)
        target = db.get(IntelligenceItem, current.merged_into_id)
        if target is None:
            raise RuntimeError("情报合并目标不存在")
        current = target
    return current


class RunService:
    def __init__(self, db: Session, hermes_client: HermesClient) -> None:
        self.db = db
        self.hermes_client = hermes_client

    async def execute_task(self, task_id: int) -> None:
        task = self.db.get(TaskRun, task_id)
        if task is None:
            raise ValueError(f"TaskRun {task_id} does not exist")

        task.status = "running"
        task.stage = "processing"
        task.origin = "subscription-hermes"
        task.topic = task.topic or task.subscription.name
        task.request_summary = task.request_summary or task.subscription.prompt[:1000]
        task.error_message = None
        self.db.commit()
        started = time.perf_counter()

        retrying = False
        try:
            result = await self.hermes_client.execute(task.subscription.prompt)
            task.hermes_run_id = result.run_id
            task.raw_output = result.raw_output
            task.stage = "publishing"
            self.db.commit()

            resolved_items: list[tuple[IntelligenceItem, bool]] = []
            seen_item_ids: set[int] = set()
            for item in result.items:
                fingerprint = item_fingerprint(item.title, item.url)
                existing = self.db.scalar(
                    select(IntelligenceItem).where(IntelligenceItem.fingerprint == fingerprint)
                )
                if existing is not None:
                    existing = canonical_item(self.db, existing)
                    if existing.id not in seen_item_ids:
                        resolved_items.append((existing, False))
                        seen_item_ids.add(existing.id)
                    continue
                record = IntelligenceItem(
                    subscription_id=task.subscription_id,
                    kind=item.kind,
                    title=item.title,
                    summary=item.summary,
                    url=normalize_url(item.url),
                    source=item.source,
                    published_at=item.published_at,
                    keywords_json=json.dumps(item.keywords, ensure_ascii=False),
                    reason=item.reason,
                    importance=max(0, min(item.importance, 1)),
                    fingerprint=fingerprint,
                )
                self.db.add(record)
                self.db.flush()
                resolved_items.append((record, True))
                seen_item_ids.add(record.id)

            briefing = Briefing(
                subscription_id=task.subscription_id,
                title=result.briefing.title,
                kind=result.briefing.kind,
                content=result.briefing.content,
                item_count=len(resolved_items),
                period_start=result.briefing.period_start,
                period_end=result.briefing.period_end,
            )
            self.db.add(briefing)
            self.db.flush()

            inserted = sum(was_inserted for _, was_inserted in resolved_items)
            trace_id = f"task-run:{task.id}"
            publication = HermesPublication(
                idempotency_key=trace_id,
                payload_hash=hashlib.sha256(trace_id.encode()).hexdigest(),
                subscription_id=task.subscription_id,
                briefing_id=briefing.id,
                trace_id=trace_id,
                hermes_run_id=result.run_id,
                task_run_id=task.id,
                item_count=inserted,
                skipped_count=len(resolved_items) - inserted,
                topic=task.subscription.name,
                request_summary=task.subscription.prompt[:1000],
                origin="subscription-hermes",
            )
            self.db.add(publication)
            self.db.flush()
            self.db.add_all(
                PublicationItem(
                    publication_id=publication.id,
                    item_id=item.id,
                    ordinal=ordinal,
                    was_inserted=was_inserted,
                )
                for ordinal, (item, was_inserted) in enumerate(resolved_items)
            )
            record_quality_decisions(self.db, publication, result.items, resolved_items)
            task.subscription.last_run_at = datetime.now(timezone.utc)
            task.status = "success"
            task.stage = "completed"
            task.result_summary = (
                f"新增{inserted}条情报，复用{len(resolved_items) - inserted}条，"
                f"生成报告《{briefing.title}》"
            )
        except (HermesUnavailable, HermesTimeout) as exc:
            self.db.rollback()
            task = self.db.get(TaskRun, task_id)
            if task is None:
                raise
            if task.retry_count < 2:
                task.retry_count += 1
                task.status = "queued"
                task.stage = "accepted"
                task.error_message = f"第{task.retry_count}次尝试失败，将自动重试：{str(exc)[:1800]}"
                task.finished_at = None
                task.duration_ms = None
                retrying = True
            else:
                task.status = "failed"
                task.stage = "failed"
                task.error_message = str(exc)[:2000]
        except Exception as exc:
            self.db.rollback()
            task = self.db.get(TaskRun, task_id)
            if task is None:
                raise
            task.status = "failed"
            task.stage = "failed"
            task.error_message = str(exc)[:2000]
        finally:
            if not retrying:
                task.finished_at = datetime.now(timezone.utc)
                task.duration_ms = int((time.perf_counter() - started) * 1000)
            self.db.commit()
