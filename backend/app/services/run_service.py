import hashlib
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Briefing, HermesPublication, IntelligenceItem, PublicationItem, TaskRun
from app.services.hermes import HermesClient


def normalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def item_fingerprint(title: str, url: str) -> str:
    normalized_title = " ".join(title.casefold().split())
    normalized_url = normalize_url(url).rstrip("/")
    return hashlib.sha256(f"{normalized_title}\n{normalized_url}".encode()).hexdigest()


class RunService:
    def __init__(self, db: Session, hermes_client: HermesClient) -> None:
        self.db = db
        self.hermes_client = hermes_client

    async def execute_task(self, task_id: int) -> None:
        task = self.db.get(TaskRun, task_id)
        if task is None:
            raise ValueError(f"TaskRun {task_id} does not exist")

        task.status = "running"
        task.error_message = None
        self.db.commit()
        started = time.perf_counter()

        try:
            result = await self.hermes_client.execute(task.subscription.prompt)
            task.hermes_run_id = result.run_id
            task.raw_output = result.raw_output

            resolved_items: list[tuple[IntelligenceItem, bool]] = []
            for item in result.items:
                fingerprint = item_fingerprint(item.title, item.url)
                existing = self.db.scalar(
                    select(IntelligenceItem).where(IntelligenceItem.fingerprint == fingerprint)
                )
                if existing is not None:
                    resolved_items.append((existing, False))
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
            task.subscription.last_run_at = datetime.now(timezone.utc)
            task.status = "success"
        except Exception as exc:
            self.db.rollback()
            task = self.db.get(TaskRun, task_id)
            if task is None:
                raise
            task.status = "failed"
            task.error_message = str(exc)[:2000]
        finally:
            task.finished_at = datetime.now(timezone.utc)
            task.duration_ms = int((time.perf_counter() - started) * 1000)
            self.db.commit()
