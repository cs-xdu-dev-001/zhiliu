import json
import ipaddress
import os
import re
import socket
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Iterator, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import Select, exists, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Briefing,
    HermesPreference,
    HermesPublication,
    IntelligenceItem,
    ItemTag,
    ItemTopic,
    PublicationItem,
    Subscription,
    TaskRun,
    Topic,
    TopicAlias,
)

ExportFormat = Literal["json", "markdown"]
ExportSection = Literal["items", "reports", "sources", "tags", "topics", "preferences", "tasks"]
ALL_SECTIONS: tuple[ExportSection, ...] = (
    "items", "reports", "sources", "tags", "topics", "preferences", "tasks",
)

SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|mcp[_-]?token|authorization|encryption[_-]?key|secret|password)"
    r"\s*[:=]\s*([^\s,;]+)"
)
BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
URL_IN_TEXT = re.compile(r"https?://[^\s<>\]\[()]+", re.IGNORECASE)
INTERNAL_HOST = re.compile(
    r"(?i)^(localhost|host\.docker\.internal|0\.0\.0\.0|127(?:\.\d{1,3}){3}|10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})$"
)
SENSITIVE_QUERY_KEYS = {
    "api_key", "apikey", "access_token", "token", "authorization", "secret", "password", "signature", "key",
}


@dataclass(frozen=True)
class ExportFilters:
    from_date: date | None = None
    to_date: date | None = None
    topic_id: int | None = None
    kind: str | None = None
    sections: tuple[ExportSection, ...] = ALL_SECTIONS


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def safe_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value.strip())
        hostname = parsed.hostname
        parsed_port = parsed.port
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not hostname or is_internal_host(hostname):
        return None
    port = f":{parsed_port}" if parsed_port else ""
    host_for_url = f"[{hostname}]" if ":" in hostname else hostname
    netloc = f"{host_for_url}{port}"
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold().replace("-", "_") not in SENSITIVE_QUERY_KEYS
        ],
        doseq=True,
    )
    return urlunsplit((parsed.scheme, netloc, parsed.path, query, ""))


def is_internal_host(hostname: str) -> bool:
    normalized = hostname.casefold().rstrip(".")
    if INTERNAL_HOST.match(normalized) or normalized.endswith((".local", ".internal")):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        try:
            legacy_ipv4 = ipaddress.ip_address(socket.inet_aton(normalized))
        except OSError:
            legacy_ipv4 = None
        if legacy_ipv4 is not None:
            return legacy_ipv4.is_private or legacy_ipv4.is_loopback or legacy_ipv4.is_link_local or legacy_ipv4.is_unspecified
        for suffix in (".nip.io", ".sslip.io"):
            if normalized.endswith(suffix):
                encoded = normalized.removesuffix(suffix).replace("-", ".")
                try:
                    resolved = ipaddress.ip_address(encoded)
                except ValueError:
                    break
                return resolved.is_private or resolved.is_loopback or resolved.is_link_local or resolved.is_unspecified
        return "." not in normalized
    return address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified


def clean_text(value: str | None, *, limit: int | None = None) -> str:
    text = value or ""
    text = BEARER_TOKEN.sub("Bearer [已移除]", text)
    text = SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[已移除]", text)
    text = URL_IN_TEXT.sub(lambda match: safe_url(match.group(0)) or "[内部地址已移除]", text)
    if limit is not None and len(text) > limit:
        return f"{text[:limit].rstrip()}…"
    return text


def json_value(value: str, fallback):
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return fallback
    return decoded


class DataExportService:
    def __init__(self, db: Session, filters: ExportFilters) -> None:
        self.db = db
        self.filters = filters
        self.topic = db.get(Topic, filters.topic_id) if filters.topic_id else None
        if filters.topic_id and (self.topic is None or self.topic.merged_into_id is not None):
            raise LookupError("主题不存在")

    def build(self, export_format: ExportFormat) -> tuple[Path, dict[str, int]]:
        suffix = ".json" if export_format == "json" else ".md"
        descriptor, raw_path = tempfile.mkstemp(prefix="zhiliu-export-", suffix=suffix)
        os.close(descriptor)
        path = Path(raw_path)
        path.chmod(0o600)
        counts: dict[str, int] = {}
        try:
            with path.open("w", encoding="utf-8", newline="\n") as stream:
                if export_format == "json":
                    self._write_json(stream, counts)
                else:
                    self._write_markdown(stream, counts)
                stream.flush()
                os.fsync(stream.fileno())
            return path, counts
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def _date_filters(self, column) -> list:
        filters = []
        if self.filters.from_date:
            filters.append(column >= datetime.combine(self.filters.from_date, time.min, tzinfo=timezone.utc))
        if self.filters.to_date:
            filters.append(column < datetime.combine(self.filters.to_date + timedelta(days=1), time.min, tzinfo=timezone.utc))
        return filters

    def _item_ids(self) -> Select:
        statement = select(IntelligenceItem.id)
        conditions = self._date_filters(IntelligenceItem.created_at)
        if self.filters.kind:
            conditions.append(IntelligenceItem.kind == self.filters.kind)
        if self.filters.topic_id:
            conditions.append(exists(select(ItemTopic.id).where(
                ItemTopic.item_id == IntelligenceItem.id,
                ItemTopic.topic_id == self.filters.topic_id,
            )))
        return statement.where(*conditions)

    def _items(self) -> Iterator[dict]:
        statement = select(IntelligenceItem).where(IntelligenceItem.id.in_(self._item_ids())).order_by(IntelligenceItem.id)
        for item in self.db.scalars(statement.execution_options(yield_per=200)):
            yield {
                "id": item.id,
                "subscriptionId": item.subscription_id,
                "kind": item.kind,
                "title": clean_text(item.title),
                "summary": clean_text(item.summary),
                "originalUrl": safe_url(item.url),
                "source": clean_text(item.source),
                "publishedAt": iso(item.published_at),
                "keywords": [clean_text(str(value), limit=120) for value in json_value(item.keywords_json, []) if isinstance(value, str)],
                "reason": clean_text(item.reason),
                "importance": item.importance,
                "fingerprint": item.fingerprint,
                "isRead": item.is_read,
                "isSaved": item.is_saved,
                "isIgnored": item.is_ignored,
                "isInvalid": item.is_invalid,
                "sourceUnavailable": item.source_unavailable,
                "latestChangeType": item.latest_change_type,
                "mergedIntoId": item.merged_into_id,
                "createdAt": iso(item.created_at),
            }

    def _sources(self) -> Iterator[dict]:
        statement = select(
            IntelligenceItem.id,
            IntelligenceItem.source,
            IntelligenceItem.url,
            IntelligenceItem.source_unavailable,
        ).where(IntelligenceItem.id.in_(self._item_ids())).order_by(IntelligenceItem.id)
        for item_id, source, url, unavailable in self.db.execute(statement.execution_options(yield_per=300)):
            yield {"itemId": item_id, "name": clean_text(source), "originalUrl": safe_url(url), "unavailable": unavailable}

    def _tags(self) -> Iterator[dict]:
        statement = select(ItemTag.item_id, ItemTag.name, ItemTag.created_at).where(
            ItemTag.item_id.in_(self._item_ids())
        ).order_by(ItemTag.item_id, ItemTag.name)
        for item_id, name, created_at in self.db.execute(statement.execution_options(yield_per=500)):
            yield {"itemId": item_id, "name": clean_text(name, limit=120), "createdAt": iso(created_at)}

    def _topics(self) -> Iterator[dict]:
        if self.filters.topic_id:
            statement = select(Topic).where(Topic.id == self.filters.topic_id)
        elif self.filters.from_date or self.filters.to_date or self.filters.kind:
            linked_topics = select(ItemTopic.topic_id).where(ItemTopic.item_id.in_(self._item_ids()))
            statement = select(Topic).where(Topic.id.in_(linked_topics))
        else:
            statement = select(Topic)
        for topic in self.db.scalars(statement.order_by(Topic.id).execution_options(yield_per=100)):
            aliases = list(self.db.scalars(select(TopicAlias.name).where(TopicAlias.topic_id == topic.id).order_by(TopicAlias.id)))
            yield {
                "id": topic.id,
                "name": clean_text(topic.name),
                "description": clean_text(topic.description),
                "aliases": [clean_text(alias, limit=120) for alias in aliases],
                "isFollowed": topic.is_followed,
                "isPinned": topic.is_pinned,
                "isMuted": topic.is_muted,
                "mergedIntoId": topic.merged_into_id,
                "createdAt": iso(topic.created_at),
                "updatedAt": iso(topic.updated_at),
            }

    def _item_topics(self) -> Iterator[dict]:
        statement = select(ItemTopic).where(ItemTopic.item_id.in_(self._item_ids())).order_by(ItemTopic.item_id, ItemTopic.topic_id)
        for link in self.db.scalars(statement.execution_options(yield_per=500)):
            yield {"itemId": link.item_id, "topicId": link.topic_id, "source": link.source, "confidence": link.confidence}

    def _briefing_ids(self) -> Select:
        statement = select(Briefing.id)
        conditions = self._date_filters(Briefing.created_at)
        if self.filters.kind:
            conditions.append(Briefing.kind == self.filters.kind)
        if self.filters.topic_id:
            conditions.append(exists(
                select(HermesPublication.id)
                .join(PublicationItem, PublicationItem.publication_id == HermesPublication.id)
                .join(ItemTopic, ItemTopic.item_id == PublicationItem.item_id)
                .where(HermesPublication.briefing_id == Briefing.id, ItemTopic.topic_id == self.filters.topic_id)
            ))
        return statement.where(*conditions)

    def _reports(self) -> Iterator[dict]:
        statement = select(Briefing).where(Briefing.id.in_(self._briefing_ids())).order_by(Briefing.id)
        for report in self.db.scalars(statement.execution_options(yield_per=100)):
            yield {
                "id": report.id,
                "subscriptionId": report.subscription_id,
                "title": clean_text(report.title),
                "kind": report.kind,
                "content": clean_text(report.content),
                "itemCount": report.item_count,
                "periodStart": iso(report.period_start),
                "periodEnd": iso(report.period_end),
                "seriesId": report.series_id,
                "versionNumber": report.version_number,
                "previousVersionId": report.previous_version_id,
                "generationTaskId": report.generation_task_id,
                "citationStatus": report.citation_status,
                "citationWarnings": [clean_text(str(value)) for value in report.citation_warnings],
                "createdAt": iso(report.created_at),
            }

    def _report_sources(self) -> Iterator[dict]:
        statement = (
            select(
                HermesPublication.briefing_id,
                HermesPublication.id,
                PublicationItem.item_id,
                PublicationItem.ordinal,
                PublicationItem.was_inserted,
                IntelligenceItem.title,
                IntelligenceItem.summary,
                IntelligenceItem.kind,
                IntelligenceItem.published_at,
                IntelligenceItem.fingerprint,
                IntelligenceItem.source,
                IntelligenceItem.url,
            )
            .join(PublicationItem, PublicationItem.publication_id == HermesPublication.id)
            .join(IntelligenceItem, IntelligenceItem.id == PublicationItem.item_id)
            .where(HermesPublication.briefing_id.in_(self._briefing_ids()))
            .order_by(HermesPublication.briefing_id, PublicationItem.ordinal)
        )
        for briefing_id, publication_id, item_id, ordinal, was_inserted, title, summary, kind, published_at, fingerprint, source, url in self.db.execute(
            statement.execution_options(yield_per=500)
        ):
            yield {
                "reportId": briefing_id,
                "publicationId": publication_id,
                "itemId": item_id,
                "ordinal": ordinal,
                "wasInserted": was_inserted,
                "title": clean_text(title),
                "summary": clean_text(summary),
                "kind": kind,
                "publishedAt": iso(published_at),
                "fingerprint": fingerprint,
                "source": clean_text(source),
                "originalUrl": safe_url(url),
            }

    def _subscription_refs(self) -> Iterator[dict]:
        selected = set(self.filters.sections)
        conditions = []
        if "items" in selected:
            conditions.append(Subscription.id.in_(
                select(IntelligenceItem.subscription_id).where(IntelligenceItem.id.in_(self._item_ids()))
            ))
        if "reports" in selected:
            conditions.append(Subscription.id.in_(
                select(Briefing.subscription_id).where(Briefing.id.in_(self._briefing_ids()))
            ))
        if "tasks" in selected:
            conditions.append(Subscription.id.in_(
                select(TaskRun.subscription_id).where(TaskRun.id.in_(self._task_ids()))
            ))
        if not conditions:
            return
        statement = select(Subscription).where(or_(*conditions)).order_by(Subscription.id)
        for subscription in self.db.scalars(statement.execution_options(yield_per=100)):
            yield {
                "id": subscription.id,
                "name": clean_text(subscription.name, limit=120),
                "kind": subscription.kind,
            }

    def _preferences(self) -> Iterator[dict]:
        conditions = self._date_filters(HermesPreference.created_at)
        if self.filters.kind:
            conditions.append(HermesPreference.kind.in_(("all", self.filters.kind)))
        if self.topic:
            conditions.append(HermesPreference.scope == "topic")
            conditions.append(HermesPreference.value == self.topic.name)
        statement = select(HermesPreference).where(*conditions).order_by(HermesPreference.id)
        for preference in self.db.scalars(statement.execution_options(yield_per=200)):
            yield {
                "id": preference.id,
                "scope": preference.scope,
                "effect": preference.effect,
                "value": clean_text(preference.value),
                "kind": preference.kind,
                "note": clean_text(preference.note),
                "active": preference.active,
                "createdAt": iso(preference.created_at),
                "updatedAt": iso(preference.updated_at),
            }

    def _task_ids(self) -> Select:
        statement = select(TaskRun.id).join(Subscription, Subscription.id == TaskRun.subscription_id)
        conditions = self._date_filters(TaskRun.started_at)
        if self.filters.kind:
            conditions.append(Subscription.kind == self.filters.kind)
        if self.topic:
            relevant_publications = select(HermesPublication.task_run_id).join(
                PublicationItem, PublicationItem.publication_id == HermesPublication.id
            ).where(PublicationItem.item_id.in_(self._item_ids()))
            conditions.append(or_(TaskRun.topic == self.topic.name, TaskRun.id.in_(relevant_publications)))
        return statement.where(*conditions)

    def _tasks(self) -> Iterator[dict]:
        statement = select(TaskRun).where(TaskRun.id.in_(self._task_ids())).order_by(TaskRun.id)
        for task in self.db.scalars(statement.execution_options(yield_per=200)):
            yield {
                "id": task.id,
                "subscriptionId": task.subscription_id,
                "retryOfId": task.retry_of_id,
                "traceId": task.trace_id,
                "origin": task.origin,
                "topic": clean_text(task.topic),
                "status": task.status,
                "stage": task.stage,
                "resultSummary": clean_text(task.result_summary, limit=1000),
                "startedAt": iso(task.started_at),
                "finishedAt": iso(task.finished_at),
                "cancelledAt": iso(task.cancelled_at),
                "durationMs": task.duration_ms,
                "retryCount": task.retry_count,
                "reportSeriesId": task.report_series_id,
                "reportVersionNumber": task.report_version_number,
            }

    def _publications(self) -> Iterator[dict]:
        statement = select(HermesPublication).where(HermesPublication.task_run_id.in_(self._task_ids())).order_by(HermesPublication.id)
        for publication in self.db.scalars(statement.execution_options(yield_per=200)):
            yield {
                "id": publication.id,
                "subscriptionId": publication.subscription_id,
                "briefingId": publication.briefing_id,
                "taskRunId": publication.task_run_id,
                "traceId": publication.trace_id,
                "topic": clean_text(publication.topic),
                "origin": publication.origin,
                "itemCount": publication.item_count,
                "skippedCount": publication.skipped_count,
                "filteredCount": publication.filtered_count,
                "createdAt": iso(publication.created_at),
            }

    def _datasets(self) -> list[tuple[str, Callable[[], Iterator[dict]]]]:
        datasets: list[tuple[str, Callable[[], Iterator[dict]]]] = []
        selected = set(self.filters.sections)
        if selected & {"items", "reports", "tasks"}:
            datasets.append(("subscriptionRefs", self._subscription_refs))
        if "items" in selected:
            datasets.append(("items", self._items))
        if "reports" in selected:
            datasets.extend((("reports", self._reports), ("reportSources", self._report_sources)))
        if "sources" in selected:
            datasets.append(("sources", self._sources))
        if "tags" in selected:
            datasets.append(("tags", self._tags))
        if "topics" in selected:
            datasets.extend((("topics", self._topics), ("itemTopics", self._item_topics)))
        if "preferences" in selected:
            datasets.append(("preferences", self._preferences))
        if "tasks" in selected:
            datasets.extend((("tasks", self._tasks), ("publications", self._publications)))
        return datasets

    def _filter_manifest(self) -> dict:
        return {
            "fromDate": self.filters.from_date.isoformat() if self.filters.from_date else None,
            "toDate": self.filters.to_date.isoformat() if self.filters.to_date else None,
            "topicId": self.filters.topic_id,
            "kind": self.filters.kind,
            "sections": list(self.filters.sections),
        }

    @staticmethod
    def _write_array(stream, values: Iterable[dict]) -> int:
        count = 0
        stream.write("[")
        for value in values:
            if count:
                stream.write(",")
            stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            count += 1
        stream.write("]")
        return count

    def _write_json(self, stream, counts: dict[str, int]) -> None:
        stream.write('{"schemaVersion":1,"exportedAt":')
        stream.write(json.dumps(datetime.now(timezone.utc).isoformat()))
        stream.write(',"filters":')
        stream.write(json.dumps(self._filter_manifest(), ensure_ascii=False, separators=(",", ":")))
        stream.write(',"data":{')
        for index, (name, factory) in enumerate(self._datasets()):
            if index:
                stream.write(",")
            stream.write(json.dumps(name))
            stream.write(":")
            counts[name] = self._write_array(stream, factory())
        stream.write('},"counts":')
        stream.write(json.dumps(counts, ensure_ascii=False, separators=(",", ":")))
        stream.write("}")

    def _write_markdown(self, stream, counts: dict[str, int]) -> None:
        stream.write("# 知流数据导出\n\n")
        stream.write(f"- schemaVersion：1\n- exportedAt：{datetime.now(timezone.utc).isoformat()}\n")
        stream.write(f"- filters：`{json.dumps(self._filter_manifest(), ensure_ascii=False)}`\n\n")
        for name, factory in self._datasets():
            stream.write(f"## {name}\n\n")
            count = 0
            for value in factory():
                count += 1
                title = value.get("title") or value.get("name") or value.get("topic") or f"#{value.get('id', count)}"
                stream.write(f"### {clean_text(str(title))}\n\n")
                for key, item in value.items():
                    if key in {"title", "name"}:
                        continue
                    if key == "originalUrl" and item:
                        stream.write(f"- {key}：[打开原文](<{item}>)\n")
                    elif isinstance(item, (dict, list)):
                        stream.write(f"- {key}：`{json.dumps(item, ensure_ascii=False)}`\n")
                    else:
                        stream.write(f"- {key}：{item if item is not None else ''}\n")
                stream.write("\n")
            if count == 0:
                stream.write("无记录。\n\n")
            counts[name] = count
        stream.write("## counts\n\n")
        stream.write(f"```json\n{json.dumps(counts, ensure_ascii=False, indent=2)}\n```\n")
