from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Briefing,
    ContentFeedback,
    HermesPreference,
    HermesPublication,
    ImportBatch,
    ImportBatchRecord,
    IntelligenceItem,
    ItemChange,
    ItemRevision,
    ItemTag,
    ItemTopic,
    PublicationItem,
    Subscription,
    TaskRun,
    Topic,
    TopicAlias,
    utc_now,
)
from app.services.data_export import clean_text, safe_url
from app.services.run_service import item_fingerprint
from app.services.topics import normalize_topic

MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_IMPORT_RECORDS = 10_000
MAX_JSON_NODES = 200_000
MAX_JSON_DEPTH = 16
MAX_JSON_STRING = 200_000
TOKEN_TTL_SECONDS = 30 * 60

ReportConflict = Literal["keep", "new_version"]

ROOT_FIELDS = {"schemaVersion", "exportedAt", "filters", "data", "counts"}
DATASETS = {
    "subscriptionRefs", "items", "reports", "reportSources", "sources", "tags",
    "topics", "itemTopics", "preferences", "tasks", "publications",
}
IMPORTABLE_DATASETS = {
    "subscriptionRefs", "items", "reports", "reportSources", "tags", "topics",
    "itemTopics", "preferences",
}
SKIPPED_DATASETS = {"sources", "tasks", "publications"}

FIELD_RULES: dict[str, tuple[set[str], set[str]]] = {
    "subscriptionRefs": (
        {"id", "name", "kind", "notifyWechat"},
        {"id", "name", "kind"},
    ),
    "items": (
        {
            "id", "subscriptionId", "kind", "title", "summary", "originalUrl", "source",
            "publishedAt", "keywords", "reason", "importance", "fingerprint", "isRead",
            "isSaved", "isIgnored", "isInvalid", "sourceUnavailable", "latestChangeType",
            "mergedIntoId", "createdAt",
        },
        {"id", "subscriptionId", "kind", "title", "summary", "source"},
    ),
    "reports": (
        {
            "id", "subscriptionId", "title", "kind", "content", "itemCount", "periodStart",
            "periodEnd", "seriesId", "versionNumber", "previousVersionId", "generationTaskId",
            "citationStatus", "citationWarnings", "createdAt",
        },
        {"id", "subscriptionId", "title", "kind", "content"},
    ),
    "reportSources": (
        {
            "reportId", "publicationId", "itemId", "ordinal", "wasInserted", "title", "summary",
            "kind", "publishedAt", "fingerprint", "source", "originalUrl",
        },
        {"reportId", "itemId", "title", "source"},
    ),
    "sources": (
        {"itemId", "name", "originalUrl", "unavailable"},
        {"itemId", "name"},
    ),
    "tags": (
        {"itemId", "name", "createdAt"},
        {"itemId", "name"},
    ),
    "topics": (
        {
            "id", "name", "description", "aliases", "isFollowed", "isPinned", "isMuted",
            "mergedIntoId", "createdAt", "updatedAt",
        },
        {"id", "name"},
    ),
    "itemTopics": (
        {"itemId", "topicId", "source", "confidence"},
        {"itemId", "topicId"},
    ),
    "preferences": (
        {"id", "scope", "effect", "value", "kind", "note", "active", "createdAt", "updatedAt"},
        {"id", "scope", "effect", "value", "kind"},
    ),
    "tasks": (
        {
            "id", "subscriptionId", "retryOfId", "traceId", "origin", "topic", "status", "stage",
            "resultSummary", "startedAt", "finishedAt", "cancelledAt", "durationMs", "retryCount",
            "reportSeriesId", "reportVersionNumber",
            "notificationStatus", "notificationError", "notificationSentAt",
        },
        {"id"},
    ),
    "publications": (
        {
            "id", "subscriptionId", "briefingId", "taskRunId", "traceId", "topic", "origin",
            "itemCount", "skippedCount", "filteredCount", "createdAt",
        },
        {"id"},
    ),
}


class ImportValidationError(ValueError):
    def __init__(self, message: str, *, path: str | None = None) -> None:
        super().__init__(message)
        self.path = path


class ImportConflictError(RuntimeError):
    pass


def _duplicate_key_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ImportValidationError(f"JSON包含重复字段：{key}")
        result[key] = value
    return result


def parse_import_payload(raw: bytes) -> dict[str, Any]:
    if not raw:
        raise ImportValidationError("请选择非空的知流JSON文件")
    if len(raw) > MAX_IMPORT_BYTES:
        raise ImportValidationError("文件超过10MiB限制")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ImportValidationError("文件必须使用UTF-8编码") from error
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_duplicate_key_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ImportValidationError(f"JSON不能包含{value}")
            ),
        )
    except ImportValidationError:
        raise
    except json.JSONDecodeError as error:
        raise ImportValidationError(f"JSON格式错误：第{error.lineno}行第{error.colno}列") from error
    if not isinstance(payload, dict):
        raise ImportValidationError("文件顶层必须是JSON对象")
    _validate_shape_limits(payload)
    _validate_export_contract(payload)
    return payload


def _validate_shape_limits(payload: Any) -> None:
    nodes = 0
    stack: list[tuple[Any, int]] = [(payload, 1)]
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise ImportValidationError("JSON结构过大")
        if depth > MAX_JSON_DEPTH:
            raise ImportValidationError("JSON嵌套层级超过限制")
        if isinstance(value, str) and len(value) > MAX_JSON_STRING:
            raise ImportValidationError("JSON包含过长文本")
        if isinstance(value, float) and not math.isfinite(value):
            raise ImportValidationError("JSON不能包含非有限数值")
        if isinstance(value, dict):
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)


def _validate_export_contract(payload: dict[str, Any]) -> None:
    unknown_root = set(payload) - ROOT_FIELDS
    if unknown_root:
        raise ImportValidationError(f"文件包含未知顶层字段：{sorted(unknown_root)[0]}")
    if payload.get("schemaVersion") != 1:
        raise ImportValidationError("仅支持schemaVersion=1的知流导出文件")
    data = payload.get("data")
    counts = payload.get("counts")
    if not isinstance(data, dict) or not isinstance(counts, dict):
        raise ImportValidationError("文件缺少data或counts对象")
    unknown_datasets = set(data) - DATASETS
    if unknown_datasets:
        raise ImportValidationError(f"文件包含未知数据集：{sorted(unknown_datasets)[0]}")
    if set(counts) != set(data):
        raise ImportValidationError("counts与data的数据集不一致")
    total = 0
    for name, records in data.items():
        if not isinstance(records, list):
            raise ImportValidationError(f"data.{name}必须是数组")
        if type(counts[name]) is not int or counts[name] != len(records):
            raise ImportValidationError(f"data.{name}计数不一致")
        total += len(records)
        allowed, required = FIELD_RULES[name]
        for index, record in enumerate(records):
            path = f"data.{name}[{index}]"
            if not isinstance(record, dict):
                raise ImportValidationError("记录必须是对象", path=path)
            unknown = set(record) - allowed
            missing = required - set(record)
            if unknown:
                raise ImportValidationError(f"包含未知字段：{sorted(unknown)[0]}", path=path)
            if missing:
                raise ImportValidationError(f"缺少字段：{sorted(missing)[0]}", path=path)
            _validate_record_types(name, record, path)
    if total > MAX_IMPORT_RECORDS:
        raise ImportValidationError("文件记录总数超过10000条限制")
    _validate_unique_ids(data)
    _validate_relations(data)
    _validate_merge_cycles(data)
    _validate_report_version_cycles(data)


def _is_int(value: Any) -> bool:
    return type(value) is int


def _validate_record_types(name: str, record: dict[str, Any], path: str) -> None:
    id_fields = {
        "id", "subscriptionId", "reportId", "publicationId", "itemId", "topicId",
        "previousVersionId", "generationTaskId", "mergedIntoId", "retryOfId", "taskRunId",
    }
    for field in id_fields & set(record):
        value = record[field]
        if value is not None and (not _is_int(value) or value <= 0):
            raise ImportValidationError(f"{field}必须是正整数或null", path=path)
    for field in {"name", "title", "summary", "content", "source", "value", "scope", "effect", "kind"} & set(record):
        if not isinstance(record[field], str):
            raise ImportValidationError(f"{field}必须是字符串", path=path)
    for field in {"isRead", "isSaved", "isIgnored", "isInvalid", "sourceUnavailable", "isFollowed", "isPinned", "isMuted", "active", "wasInserted", "unavailable"} & set(record):
        if not isinstance(record[field], bool):
            raise ImportValidationError(f"{field}必须是布尔值", path=path)
    for field in {"importance", "confidence"} & set(record):
        value = record[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ImportValidationError(f"{field}必须是有限数值", path=path)
        if not 0 <= float(value) <= 1:
            raise ImportValidationError(f"{field}必须在0到1之间", path=path)
    integer_fields = {
        "itemCount", "versionNumber", "ordinal", "durationMs", "retryCount",
        "reportVersionNumber", "skippedCount", "filteredCount",
    }
    for field in integer_fields & set(record):
        value = record[field]
        if value is not None and (not _is_int(value) or value < 0):
            raise ImportValidationError(f"{field}必须是非负整数或null", path=path)
        if field in {"versionNumber", "ordinal"} and value is not None and value < 1:
            raise ImportValidationError(f"{field}必须大于0", path=path)
    for field in {"keywords", "aliases", "citationWarnings"} & set(record):
        value = record[field]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ImportValidationError(f"{field}必须是字符串数组", path=path)
    if record.get("kind") not in {None, "news", "paper", "job", "all"}:
        raise ImportValidationError("kind不是支持的内容类型", path=path)
    fingerprint = record.get("fingerprint")
    if fingerprint is not None and (not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", fingerprint)):
        raise ImportValidationError("fingerprint必须是64位十六进制摘要", path=path)
    for field in {
        "publishedAt", "createdAt", "updatedAt", "periodStart", "periodEnd", "startedAt",
        "finishedAt", "cancelledAt",
    } & set(record):
        value = record[field]
        if value is None:
            continue
        if not isinstance(value, str):
            raise ImportValidationError(f"{field}必须是ISO时间字符串或null", path=path)
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ImportValidationError(f"{field}不是有效的ISO时间", path=path) from error
    if name == "items" and not record["title"].strip():
        raise ImportValidationError("情报标题不能为空", path=path)
    if name == "reports" and (not record["title"].strip() or not record["content"].strip()):
        raise ImportValidationError("报告标题和正文不能为空", path=path)


def _validate_unique_ids(data: dict[str, list[dict[str, Any]]]) -> None:
    for name in ("subscriptionRefs", "items", "reports", "topics", "preferences"):
        seen: set[int] = set()
        for index, record in enumerate(data.get(name, [])):
            source_id = record["id"]
            if source_id in seen:
                raise ImportValidationError("同一数据集包含重复ID", path=f"data.{name}[{index}].id")
            seen.add(source_id)


def _validate_relations(data: dict[str, list[dict[str, Any]]]) -> None:
    ids = {
        name: {record["id"] for record in data.get(name, [])}
        for name in ("subscriptionRefs", "items", "reports", "topics")
    }
    subscription_ids = ids["subscriptionRefs"]
    if subscription_ids:
        for name in ("items", "reports"):
            for index, record in enumerate(data.get(name, [])):
                if record["subscriptionId"] not in subscription_ids:
                    raise ImportValidationError("引用了文件中不存在的订阅", path=f"data.{name}[{index}].subscriptionId")
    for index, record in enumerate(data.get("tags", [])):
        if record["itemId"] not in ids["items"]:
            raise ImportValidationError("标签引用了文件中不存在的情报", path=f"data.tags[{index}].itemId")
    for index, record in enumerate(data.get("itemTopics", [])):
        if record["itemId"] not in ids["items"] or record["topicId"] not in ids["topics"]:
            raise ImportValidationError("主题关系引用了文件中不存在的情报或主题", path=f"data.itemTopics[{index}]")
    for index, record in enumerate(data.get("reportSources", [])):
        if record["reportId"] not in ids["reports"]:
            raise ImportValidationError("来源关系引用了文件中不存在的报告", path=f"data.reportSources[{index}].reportId")


def _validate_merge_cycles(data: dict[str, list[dict[str, Any]]]) -> None:
    for name in ("items", "topics"):
        edges = {
            record["id"]: record.get("mergedIntoId")
            for record in data.get(name, [])
            if record.get("mergedIntoId") is not None
        }
        known = {record["id"] for record in data.get(name, [])}
        for source, target in edges.items():
            if target not in known:
                raise ImportValidationError(f"{name}合并目标不在导出范围内")
            seen = {source}
            current = target
            while current in edges:
                if current in seen:
                    raise ImportValidationError(f"{name}合并关系存在循环")
                seen.add(current)
                current = edges[current]


def _validate_report_version_cycles(data: dict[str, list[dict[str, Any]]]) -> None:
    reports = data.get("reports", [])
    known = {record["id"] for record in reports}
    edges = {
        record["id"]: record.get("previousVersionId")
        for record in reports
        if record.get("previousVersionId") is not None
    }
    for source, target in edges.items():
        if target not in known:
            continue
        seen = {source}
        current = target
        while current in edges:
            if current in seen:
                raise ImportValidationError("报告版本关系存在循环")
            seen.add(current)
            current = edges[current]


def canonical_payload_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_preview_token(payload_hash: str, secret: str) -> tuple[str, datetime]:
    expires = int(time.time()) + TOKEN_TTL_SECONDS
    claims = json.dumps({"hash": payload_hash, "exp": expires, "version": 1}, separators=(",", ":")).encode()
    encoded = _b64encode(claims)
    signature = _b64encode(hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{signature}", datetime.fromtimestamp(expires, tz=timezone.utc)


def verify_preview_token(token: str, payload_hash: str, secret: str) -> None:
    try:
        encoded, signature = token.split(".", 1)
        expected = _b64encode(hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        claims = json.loads(_b64decode(encoded))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise ImportValidationError("预览凭证无效，请重新预览文件") from error
    if claims.get("hash") != payload_hash:
        raise ImportValidationError("文件已变化，请重新预览")
    if type(claims.get("exp")) is not int or claims["exp"] < int(time.time()):
        raise ImportValidationError("预览已过期，请重新预览文件")


def _json_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _parse_datetime(value: Any, field: str) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ImportValidationError(f"{field}必须是ISO时间字符串或null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ImportValidationError(f"{field}不是有效的ISO时间") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _public_url(value: Any) -> str | None:
    return safe_url(value) if isinstance(value, str) and value else None


def _clean(value: Any, limit: int) -> str:
    return clean_text(str(value or ""), limit=limit).strip()


def _summary_template() -> dict[str, dict[str, int]]:
    return {
        name: {"create": 0, "reuse": 0, "conflict": 0, "skip": 0}
        for name in ("subscriptions", "items", "topics", "preferences", "reports", "relations")
    }


class ContentImportService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def preview(self, payload: dict[str, Any], payload_hash: str) -> dict[str, Any]:
        data = payload["data"]
        summary = _summary_template()
        warnings: list[str] = []
        subscription_map = self._preview_subscriptions(data, summary)
        item_map = self._preview_items(data, summary, warnings)
        topic_map = self._preview_topics(data, summary)
        self._preview_preferences(data, summary)
        report_map = self._preview_reports(data, subscription_map, summary)

        for record in data.get("tags", []):
            summary["relations"]["create" if record["itemId"] in item_map else "skip"] += 1
        for record in data.get("itemTopics", []):
            available = record["itemId"] in item_map and record["topicId"] in topic_map
            summary["relations"]["create" if available else "skip"] += 1
        for record in data.get("reportSources", []):
            if record["reportId"] not in report_map:
                summary["relations"]["skip"] += 1
                continue
            if record["itemId"] not in item_map:
                url = _public_url(record.get("originalUrl"))
                if url and _clean(record.get("title"), 300):
                    item_map[record["itemId"]] = -1
                    summary["items"]["create"] += 1
                    warnings.append("部分报告来源不在情报导出范围内，将创建可识别的迁移来源记录")
                else:
                    summary["relations"]["skip"] += 1
                    warnings.append("部分报告来源缺少公开链接，无法恢复引用关系")
                    continue
            summary["relations"]["create"] += 1

        unsupported = {
            name: len(data.get(name, []))
            for name in SKIPPED_DATASETS
            if data.get(name)
        }
        if unsupported:
            warnings.append("任务和原始发布记录属于运行历史，仅展示数量，不写入目标系统")
        warnings = list(dict.fromkeys(warnings))
        total = sum(payload["counts"].values())
        conflicts = sum(value["conflict"] for value in summary.values())
        creates = sum(value["create"] for value in summary.values())
        return {
            "payloadHash": payload_hash,
            "schemaVersion": payload["schemaVersion"],
            "totalRecords": total,
            "summary": summary,
            "unsupported": unsupported,
            "warnings": warnings,
            "canImport": creates > 0 or conflicts == 0,
        }

    def _subscription_sources(self, data: dict[str, Any]) -> dict[int, tuple[str, str, bool | None]]:
        result = {
            record["id"]: (
                _clean(record["name"], 120),
                record["kind"],
                bool(record["notifyWechat"]) if "notifyWechat" in record else None,
            )
            for record in data.get("subscriptionRefs", [])
        }
        kinds_by_id: dict[int, str] = {}
        for name in ("items", "reports"):
            for record in data.get(name, []):
                kinds_by_id.setdefault(record["subscriptionId"], record["kind"])
        kind_labels = {"news": "热点", "paper": "论文", "job": "招聘"}
        for source_id, kind in kinds_by_id.items():
            result.setdefault(source_id, (f"迁移导入·{kind_labels.get(kind, kind)}", kind, None))
        return result

    def _preview_subscriptions(self, data: dict[str, Any], summary: dict[str, dict[str, int]]) -> dict[int, int]:
        result: dict[int, int] = {}
        for source_id, (name, kind, _) in self._subscription_sources(data).items():
            existing = self.db.scalar(select(Subscription).where(Subscription.name == name, Subscription.kind == kind))
            if existing:
                result[source_id] = existing.id
                summary["subscriptions"]["reuse"] += 1
            else:
                result[source_id] = -1
                summary["subscriptions"]["create"] += 1
        return result

    def _preview_items(self, data: dict[str, Any], summary: dict[str, dict[str, int]], warnings: list[str]) -> dict[int, int]:
        result: dict[int, int] = {}
        seen_fingerprints: set[str] = set()
        for record in data.get("items", []):
            url = _public_url(record.get("originalUrl"))
            if not url:
                summary["items"]["conflict"] += 1
                warnings.append("部分情报缺少可公开访问的HTTP(S)原文链接，已阻止导入")
                continue
            fingerprint = record.get("fingerprint")
            if not isinstance(fingerprint, str) or len(fingerprint) != 64:
                fingerprint = item_fingerprint(record["title"], url)
            existing = self.db.scalar(select(IntelligenceItem.id).where(IntelligenceItem.fingerprint == fingerprint))
            if existing or fingerprint in seen_fingerprints:
                result[record["id"]] = existing or -1
                summary["items"]["reuse"] += 1
            else:
                seen_fingerprints.add(fingerprint)
                result[record["id"]] = -1
                summary["items"]["create"] += 1
        return result

    def _preview_topics(self, data: dict[str, Any], summary: dict[str, dict[str, int]]) -> dict[int, int]:
        result: dict[int, int] = {}
        seen: set[str] = set()
        for record in data.get("topics", []):
            normalized = normalize_topic(record["name"])
            if not normalized:
                summary["topics"]["conflict"] += 1
                continue
            existing = self.db.scalar(select(Topic.id).where(Topic.normalized_name == normalized))
            if existing or normalized in seen:
                result[record["id"]] = existing or -1
                summary["topics"]["reuse"] += 1
            else:
                seen.add(normalized)
                result[record["id"]] = -1
                summary["topics"]["create"] += 1
        return result

    def _preview_preferences(self, data: dict[str, Any], summary: dict[str, dict[str, int]]) -> None:
        seen: set[tuple[str, str, str, str]] = set()
        for record in data.get("preferences", []):
            key = (record["scope"], record["effect"], record["value"], record["kind"])
            existing = self.db.scalar(select(HermesPreference.id).where(
                HermesPreference.scope == key[0], HermesPreference.effect == key[1],
                HermesPreference.value == key[2], HermesPreference.kind == key[3],
            ))
            if existing or key in seen:
                summary["preferences"]["reuse"] += 1
            else:
                seen.add(key)
                summary["preferences"]["create"] += 1

    def _preview_reports(self, data: dict[str, Any], subscription_map: dict[int, int], summary: dict[str, dict[str, int]]) -> dict[int, int]:
        result: dict[int, int] = {}
        for record in data.get("reports", []):
            if record["subscriptionId"] not in subscription_map:
                summary["reports"]["conflict"] += 1
                continue
            series_id = self._series_id(record)
            version = int(record.get("versionNumber") or 1)
            existing = self.db.scalar(select(Briefing.id).where(
                Briefing.series_id == series_id,
                Briefing.version_number == version,
            ))
            if existing:
                result[record["id"]] = existing
                summary["reports"]["conflict"] += 1
            else:
                result[record["id"]] = -1
                summary["reports"]["create"] += 1
        return result

    @staticmethod
    def _series_id(record: dict[str, Any]) -> str:
        value = record.get("seriesId")
        if isinstance(value, str) and len(value) <= 36 and value.strip():
            return value.strip()
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"zhiliu-import-report:{record['id']}:{record['title']}"))

    def commit(self, payload: dict[str, Any], payload_hash: str, report_conflict: ReportConflict) -> tuple[dict[str, Any], bool]:
        import_key = hashlib.sha256(f"{payload_hash}:{report_conflict}".encode()).hexdigest()
        existing_batch = self.db.scalar(select(ImportBatch).where(
            ImportBatch.import_key == import_key,
            ImportBatch.status == "committed",
        ))
        if existing_batch:
            return self._batch_dict(existing_batch), True

        data = payload["data"]
        summary = _summary_template()
        batch = ImportBatch(
            import_key=import_key,
            payload_hash=payload_hash,
            schema_version=payload["schemaVersion"],
            report_conflict=report_conflict,
            status="committed",
            counts_json=json.dumps(payload["counts"], ensure_ascii=False, separators=(",", ":")),
        )
        self.db.add(batch)
        created: list[tuple[str, Any, str]] = []
        relation_records: list[tuple[str, Any, str]] = []
        try:
            self.db.flush()
            subscriptions = self._commit_subscriptions(data, summary, created)
            topics = self._commit_topics(data, summary, created)
            items = self._commit_items(data, subscriptions, summary, created)
            self._commit_item_merges(data, items)
            self._commit_topic_merges(data, topics)
            self._commit_tags(data, items, summary, relation_records)
            self._commit_item_topics(data, items, topics, summary, relation_records)
            self._commit_preferences(data, summary, created)
            reports = self._commit_reports(data, subscriptions, report_conflict, summary, created)
            self._commit_report_sources(data, reports, items, subscriptions, summary, created)
            self.db.flush()
            for entity_type, target, target_key in created + relation_records:
                batch_record = ImportBatchRecord(
                    batch_id=batch.id,
                    entity_type=entity_type,
                    target_id=getattr(target, "id", None),
                    target_key=target_key,
                    after_hash=self._entity_hash(entity_type, target, target_key),
                )
                self.db.add(batch_record)
            batch.summary_json = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
            self.db.commit()
            self.db.refresh(batch)
            return self._batch_dict(batch), False
        except IntegrityError as error:
            self.db.rollback()
            concurrent = self.db.scalar(select(ImportBatch).where(
                ImportBatch.import_key == import_key,
                ImportBatch.status == "committed",
            ))
            if concurrent:
                return self._batch_dict(concurrent), True
            raise ImportConflictError("导入期间检测到并发数据冲突，请重新预览") from error
        except Exception:
            self.db.rollback()
            raise

    def _commit_subscriptions(self, data: dict[str, Any], summary: dict[str, dict[str, int]], created: list) -> dict[int, Subscription]:
        result: dict[int, Subscription] = {}
        for source_id, (name, kind, notify_wechat) in self._subscription_sources(data).items():
            existing = self.db.scalar(select(Subscription).where(Subscription.name == name, Subscription.kind == kind))
            if existing:
                if notify_wechat is not None:
                    existing.notify_wechat = notify_wechat
                result[source_id] = existing
                summary["subscriptions"]["reuse"] += 1
                continue
            record = Subscription(
                name=name,
                kind=kind,
                keywords_json="[]",
                schedule="0 0 1 1 *",
                prompt="由内容迁移创建，仅用于承载导入记录，不自动执行。",
                enabled=False,
                notify_wechat=bool(notify_wechat),
            )
            self.db.add(record)
            self.db.flush()
            result[source_id] = record
            summary["subscriptions"]["create"] += 1
            created.append(("subscription", record, str(record.id)))
        return result

    def _commit_topics(self, data: dict[str, Any], summary: dict[str, dict[str, int]], created: list) -> dict[int, Topic]:
        result: dict[int, Topic] = {}
        for source in data.get("topics", []):
            normalized = normalize_topic(source["name"])
            if not normalized:
                summary["topics"]["conflict"] += 1
                continue
            topic = self.db.scalar(select(Topic).where(Topic.normalized_name == normalized))
            if topic:
                result[source["id"]] = topic
                summary["topics"]["reuse"] += 1
                continue
            topic = Topic(
                name=_clean(source["name"], 120),
                normalized_name=normalized,
                description=_clean(source.get("description"), 10_000),
                is_followed=bool(source.get("isFollowed", False)),
                is_pinned=bool(source.get("isPinned", False)),
                is_muted=bool(source.get("isMuted", False)),
            )
            self.db.add(topic)
            self.db.flush()
            aliases = [source["name"], *source.get("aliases", [])]
            for alias_name in dict.fromkeys(_clean(value, 120) for value in aliases):
                alias_normalized = normalize_topic(alias_name)
                if not alias_normalized:
                    continue
                if self.db.scalar(select(TopicAlias.id).where(TopicAlias.normalized_name == alias_normalized)):
                    continue
                self.db.add(TopicAlias(
                    topic_id=topic.id,
                    name=alias_name,
                    normalized_name=alias_normalized,
                    source="migration",
                ))
            self.db.flush()
            result[source["id"]] = topic
            summary["topics"]["create"] += 1
            created.append(("topic", topic, str(topic.id)))
        return result

    def _commit_items(self, data: dict[str, Any], subscriptions: dict[int, Subscription], summary: dict[str, dict[str, int]], created: list) -> dict[int, IntelligenceItem]:
        result: dict[int, IntelligenceItem] = {}
        for source in data.get("items", []):
            subscription = subscriptions.get(source["subscriptionId"])
            url = _public_url(source.get("originalUrl"))
            if not subscription or not url:
                summary["items"]["conflict"] += 1
                continue
            fingerprint = source.get("fingerprint")
            if not isinstance(fingerprint, str) or len(fingerprint) != 64:
                fingerprint = item_fingerprint(source["title"], url)
            item = self.db.scalar(select(IntelligenceItem).where(IntelligenceItem.fingerprint == fingerprint))
            if item:
                result[source["id"]] = item
                summary["items"]["reuse"] += 1
                continue
            item = IntelligenceItem(
                subscription_id=subscription.id,
                kind=source["kind"],
                title=_clean(source["title"], 300),
                summary=_clean(source.get("summary"), 200_000),
                url=url,
                source=_clean(source.get("source"), 120),
                published_at=_parse_datetime(source.get("publishedAt"), "publishedAt"),
                keywords_json=json.dumps([_clean(value, 120) for value in source.get("keywords", [])], ensure_ascii=False),
                reason=_clean(source.get("reason"), 20_000),
                importance=max(0.0, min(1.0, float(source.get("importance") or 0))),
                fingerprint=fingerprint,
                is_read=bool(source.get("isRead", False)),
                is_saved=bool(source.get("isSaved", False)),
                is_ignored=bool(source.get("isIgnored", False)),
                is_invalid=bool(source.get("isInvalid", False)),
                source_unavailable=bool(source.get("sourceUnavailable", False)),
                latest_change_type=source.get("latestChangeType") if isinstance(source.get("latestChangeType"), str) else None,
                created_at=_parse_datetime(source.get("createdAt"), "createdAt") or utc_now(),
            )
            self.db.add(item)
            self.db.flush()
            result[source["id"]] = item
            summary["items"]["create"] += 1
            created.append(("item", item, str(item.id)))
        return result

    def _commit_item_merges(self, data: dict[str, Any], items: dict[int, IntelligenceItem]) -> None:
        for source in data.get("items", []):
            target_source_id = source.get("mergedIntoId")
            item = items.get(source["id"])
            target = items.get(target_source_id) if target_source_id else None
            if item and target and item.id != target.id and item.merged_into_id is None:
                item.merged_into_id = target.id

    def _commit_topic_merges(self, data: dict[str, Any], topics: dict[int, Topic]) -> None:
        for source in data.get("topics", []):
            target_source_id = source.get("mergedIntoId")
            topic = topics.get(source["id"])
            target = topics.get(target_source_id) if target_source_id else None
            if topic and target and topic.id != target.id and topic.merged_into_id is None:
                topic.merged_into_id = target.id

    def _commit_tags(self, data: dict[str, Any], items: dict[int, IntelligenceItem], summary: dict[str, dict[str, int]], relation_records: list) -> None:
        for source in data.get("tags", []):
            item = items.get(source["itemId"])
            name = _clean(source["name"], 40)
            if not item or not name:
                summary["relations"]["skip"] += 1
                continue
            key = f"{item.id}:{name}"
            if self.db.get(ItemTag, (item.id, name)):
                summary["relations"]["reuse"] += 1
                continue
            record = ItemTag(item_id=item.id, name=name, created_at=_parse_datetime(source.get("createdAt"), "createdAt") or utc_now())
            self.db.add(record)
            self.db.flush()
            summary["relations"]["create"] += 1
            relation_records.append(("item_tag", record, key))

    def _commit_item_topics(self, data: dict[str, Any], items: dict[int, IntelligenceItem], topics: dict[int, Topic], summary: dict[str, dict[str, int]], relation_records: list) -> None:
        for source in data.get("itemTopics", []):
            item = items.get(source["itemId"])
            topic = topics.get(source["topicId"])
            if not item or not topic:
                summary["relations"]["skip"] += 1
                continue
            existing = self.db.scalar(select(ItemTopic).where(ItemTopic.item_id == item.id, ItemTopic.topic_id == topic.id))
            if existing:
                summary["relations"]["reuse"] += 1
                continue
            record = ItemTopic(
                item_id=item.id,
                topic_id=topic.id,
                source=_clean(source.get("source") or "migration", 30),
                confidence=max(0.0, min(1.0, float(source.get("confidence", 1)))),
            )
            self.db.add(record)
            self.db.flush()
            summary["relations"]["create"] += 1
            relation_records.append(("item_topic", record, f"{item.id}:{topic.id}"))

    def _commit_preferences(self, data: dict[str, Any], summary: dict[str, dict[str, int]], created: list) -> None:
        for source in data.get("preferences", []):
            existing = self.db.scalar(select(HermesPreference).where(
                HermesPreference.scope == source["scope"],
                HermesPreference.effect == source["effect"],
                HermesPreference.value == source["value"],
                HermesPreference.kind == source["kind"],
            ))
            if existing:
                summary["preferences"]["reuse"] += 1
                continue
            record = HermesPreference(
                scope=_clean(source["scope"], 30),
                effect=_clean(source["effect"], 30),
                value=_clean(source["value"], 300),
                kind=source["kind"],
                note=_clean(source.get("note"), 1000),
                active=bool(source.get("active", True)),
                created_at=_parse_datetime(source.get("createdAt"), "createdAt") or utc_now(),
                updated_at=_parse_datetime(source.get("updatedAt"), "updatedAt") or utc_now(),
            )
            self.db.add(record)
            self.db.flush()
            summary["preferences"]["create"] += 1
            created.append(("preference", record, str(record.id)))

    def _commit_reports(self, data: dict[str, Any], subscriptions: dict[int, Subscription], report_conflict: ReportConflict, summary: dict[str, dict[str, int]], created: list) -> dict[int, Briefing]:
        result: dict[int, Briefing] = {}
        source_previous: dict[int, int | None] = {}
        for source in data.get("reports", []):
            subscription = subscriptions.get(source["subscriptionId"])
            if not subscription:
                summary["reports"]["conflict"] += 1
                continue
            series_id = self._series_id(source)
            requested_version = max(1, int(source.get("versionNumber") or 1))
            existing = self.db.scalar(select(Briefing).where(
                Briefing.series_id == series_id,
                Briefing.version_number == requested_version,
            ))
            previous_id: int | None = None
            version = requested_version
            if existing:
                if report_conflict == "keep":
                    summary["reports"]["conflict"] += 1
                    continue
                latest = self.db.scalar(select(Briefing).where(Briefing.series_id == series_id).order_by(Briefing.version_number.desc()))
                version = (latest.version_number if latest else 0) + 1
                previous_id = latest.id if latest else None
            report = Briefing(
                subscription_id=subscription.id,
                title=_clean(source["title"], 300),
                kind=source["kind"],
                content=_clean(source["content"], 200_000),
                item_count=max(0, int(source.get("itemCount") or 0)),
                period_start=_parse_datetime(source.get("periodStart"), "periodStart"),
                period_end=_parse_datetime(source.get("periodEnd"), "periodEnd"),
                series_id=series_id,
                version_number=version,
                previous_version_id=previous_id,
                generation_task_id=None,
                citation_status=_clean(source.get("citationStatus") or "unchecked", 30),
                citation_warnings_json=json.dumps([_clean(value, 1000) for value in source.get("citationWarnings", [])], ensure_ascii=False),
                created_at=_parse_datetime(source.get("createdAt"), "createdAt") or utc_now(),
            )
            self.db.add(report)
            self.db.flush()
            result[source["id"]] = report
            source_previous[source["id"]] = source.get("previousVersionId")
            summary["reports"]["create"] += 1
            created.append(("briefing", report, str(report.id)))
        for source_id, previous_source_id in source_previous.items():
            if previous_source_id and result.get(previous_source_id) and result[source_id].previous_version_id is None:
                result[source_id].previous_version_id = result[previous_source_id].id
        return result

    def _commit_report_sources(self, data: dict[str, Any], reports: dict[int, Briefing], items: dict[int, IntelligenceItem], subscriptions: dict[int, Subscription], summary: dict[str, dict[str, int]], created: list) -> None:
        report_records = {record["id"]: record for record in data.get("reports", [])}
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for source in data.get("reportSources", []):
            grouped[source["reportId"]].append(source)
        for source_report_id, sources in grouped.items():
            report = reports.get(source_report_id)
            if not report:
                summary["relations"]["skip"] += len(sources)
                continue
            linked_items: list[tuple[IntelligenceItem, dict[str, Any]]] = []
            for source in sorted(sources, key=lambda value: int(value.get("ordinal") or 0)):
                item = items.get(source["itemId"])
                if item is None:
                    url = _public_url(source.get("originalUrl"))
                    title = _clean(source.get("title"), 300)
                    report_source = report_records.get(source_report_id, {})
                    subscription = subscriptions.get(report_source.get("subscriptionId"))
                    if url and title and subscription:
                        fingerprint = source.get("fingerprint")
                        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
                            fingerprint = item_fingerprint(title, url)
                        item = self.db.scalar(select(IntelligenceItem).where(IntelligenceItem.fingerprint == fingerprint))
                        if item is None:
                            item = IntelligenceItem(
                                subscription_id=subscription.id,
                                kind=source.get("kind") if source.get("kind") in {"news", "paper", "job"} else report.kind,
                                title=title,
                                summary=_clean(source.get("summary") or "由迁移报告引用，原导出范围未包含完整情报。", 200_000),
                                url=url,
                                source=_clean(source.get("source"), 120),
                                published_at=_parse_datetime(source.get("publishedAt"), "publishedAt"),
                                keywords_json="[]",
                                reason="由内容迁移恢复的报告来源",
                                importance=0,
                                fingerprint=fingerprint,
                            )
                            self.db.add(item)
                            self.db.flush()
                            created.append(("item", item, str(item.id)))
                            summary["items"]["create"] += 1
                        else:
                            summary["items"]["reuse"] += 1
                        items[source["itemId"]] = item
                if item is None:
                    summary["relations"]["skip"] += 1
                    continue
                linked_items.append((item, source))
            if not linked_items:
                continue
            item_ids = [item.id for item, _ in linked_items]
            existing_publication_ids = self.db.scalars(select(HermesPublication.id).where(HermesPublication.briefing_id == report.id)).all()
            duplicate = False
            for publication_id in existing_publication_ids:
                existing_ids = list(self.db.scalars(select(PublicationItem.item_id).where(
                    PublicationItem.publication_id == publication_id
                ).order_by(PublicationItem.ordinal)))
                if existing_ids == item_ids:
                    duplicate = True
                    break
            if duplicate:
                summary["relations"]["reuse"] += len(linked_items)
                continue
            digest = _json_hash({"report": report.id, "items": item_ids, "source": "content-import"})
            publication = HermesPublication(
                idempotency_key=f"content-import:{digest[:120]}",
                payload_hash=digest,
                subscription_id=report.subscription_id,
                briefing_id=report.id,
                trace_id=None,
                hermes_run_id=None,
                task_run_id=None,
                item_count=len(linked_items),
                skipped_count=0,
                filtered_count=0,
                topic="内容迁移",
                request_summary="由知流内容迁移恢复报告来源",
                origin="content-import",
            )
            self.db.add(publication)
            self.db.flush()
            for ordinal, (item, source) in enumerate(linked_items, 1):
                self.db.add(PublicationItem(
                    publication_id=publication.id,
                    item_id=item.id,
                    ordinal=int(source.get("ordinal") or ordinal),
                    was_inserted=bool(source.get("wasInserted", False)),
                ))
            self.db.flush()
            report.item_count = len(linked_items)
            summary["relations"]["create"] += len(linked_items)
            created.append(("publication", publication, str(publication.id)))

    def list_batches(self, limit: int = 20) -> list[dict[str, Any]]:
        return [self._batch_dict(batch) for batch in self.db.scalars(
            select(ImportBatch).order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc()).limit(limit)
        )]

    def undo(self, batch_id: int) -> dict[str, Any]:
        batch = self.db.get(ImportBatch, batch_id)
        if batch is None:
            raise LookupError("迁移批次不存在")
        if batch.status == "undone":
            return self._batch_dict(batch)
        records = list(self.db.scalars(select(ImportBatchRecord).where(
            ImportBatchRecord.batch_id == batch.id
        ).order_by(ImportBatchRecord.id)))
        self._verify_undo_records(records)
        order = ["item_topic", "item_tag", "publication", "briefing", "item", "topic", "preference", "subscription"]
        by_type: dict[str, list[ImportBatchRecord]] = defaultdict(list)
        for record in records:
            by_type[record.entity_type].append(record)
        try:
            for entity_type in order:
                for record in reversed(by_type.get(entity_type, [])):
                    self._delete_record(entity_type, record)
                    self.db.flush()
            batch.status = "undone"
            batch.undone_at = utc_now()
            self.db.commit()
            self.db.refresh(batch)
            return self._batch_dict(batch)
        except Exception:
            self.db.rollback()
            raise

    def _verify_undo_records(self, records: list[ImportBatchRecord]) -> None:
        for record in records:
            target = self._load_record_target(record)
            if target is None:
                raise ImportConflictError("迁移内容已被删除或改变，无法安全撤销")
            current_hash = self._entity_hash(record.entity_type, target, record.target_key)
            if not hmac.compare_digest(current_hash, record.after_hash):
                raise ImportConflictError("迁移内容在导入后发生变化，撤销未执行")

    def _load_record_target(self, record: ImportBatchRecord) -> Any | None:
        model_map = {
            "subscription": Subscription,
            "item": IntelligenceItem,
            "topic": Topic,
            "preference": HermesPreference,
            "briefing": Briefing,
            "publication": HermesPublication,
        }
        if record.entity_type in model_map:
            return self.db.get(model_map[record.entity_type], record.target_id)
        if record.entity_type == "item_tag":
            item_id, name = record.target_key.split(":", 1)
            return self.db.get(ItemTag, (int(item_id), name))
        if record.entity_type == "item_topic":
            item_id, topic_id = map(int, record.target_key.split(":", 1))
            return self.db.scalar(select(ItemTopic).where(ItemTopic.item_id == item_id, ItemTopic.topic_id == topic_id))
        return None

    def _delete_record(self, entity_type: str, record: ImportBatchRecord) -> None:
        target = self._load_record_target(record)
        if target is None:
            raise ImportConflictError("迁移内容已变化，撤销未执行")
        if entity_type == "publication":
            self.db.query(PublicationItem).filter(PublicationItem.publication_id == target.id).delete(synchronize_session=False)
        elif entity_type == "item":
            self.db.query(ItemRevision).filter(ItemRevision.item_id == target.id).delete(synchronize_session=False)
            self.db.query(ItemChange).filter(ItemChange.item_id == target.id).delete(synchronize_session=False)
            self.db.query(ContentFeedback).filter(ContentFeedback.item_id == target.id).delete(synchronize_session=False)
        elif entity_type == "topic":
            self.db.query(TopicAlias).filter(TopicAlias.topic_id == target.id).delete(synchronize_session=False)
        elif entity_type == "subscription":
            external = (
                self.db.scalar(select(func.count()).select_from(TaskRun).where(TaskRun.subscription_id == target.id))
                + self.db.scalar(select(func.count()).select_from(IntelligenceItem).where(IntelligenceItem.subscription_id == target.id))
                + self.db.scalar(select(func.count()).select_from(Briefing).where(Briefing.subscription_id == target.id))
                + self.db.scalar(select(func.count()).select_from(HermesPublication).where(HermesPublication.subscription_id == target.id))
            )
            if external:
                raise ImportConflictError("迁移订阅已有其他内容引用，撤销未执行")
        self.db.delete(target)

    def _entity_hash(self, entity_type: str, target: Any, target_key: str) -> str:
        if entity_type == "subscription":
            value = {
                "id": target.id, "name": target.name, "kind": target.kind, "keywords": target.keywords_json,
                "schedule": target.schedule, "prompt": target.prompt, "enabled": target.enabled,
                "items": list(self.db.scalars(select(IntelligenceItem.id).where(IntelligenceItem.subscription_id == target.id).order_by(IntelligenceItem.id))),
                "briefings": list(self.db.scalars(select(Briefing.id).where(Briefing.subscription_id == target.id).order_by(Briefing.id))),
                "publications": list(self.db.scalars(select(HermesPublication.id).where(HermesPublication.subscription_id == target.id).order_by(HermesPublication.id))),
            }
        elif entity_type == "item":
            value = {
                "id": target.id, "subscription": target.subscription_id, "kind": target.kind, "title": target.title,
                "summary": target.summary, "url": target.url, "source": target.source, "published": _iso(target.published_at),
                "keywords": target.keywords_json, "reason": target.reason, "importance": target.importance,
                "fingerprint": target.fingerprint, "states": [target.is_read, target.is_saved, target.is_ignored, target.is_invalid, target.source_unavailable],
                "merged": target.merged_into_id,
                "tags": list(self.db.scalars(select(ItemTag.name).where(ItemTag.item_id == target.id).order_by(ItemTag.name))),
                "topics": list(self.db.scalars(select(ItemTopic.topic_id).where(ItemTopic.item_id == target.id).order_by(ItemTopic.topic_id))),
                "publications": list(self.db.scalars(select(PublicationItem.publication_id).where(PublicationItem.item_id == target.id).order_by(PublicationItem.publication_id))),
                "revisions": list(self.db.scalars(select(ItemRevision.id).where(ItemRevision.item_id == target.id).order_by(ItemRevision.id))),
                "changes": list(self.db.scalars(select(ItemChange.id).where(ItemChange.item_id == target.id).order_by(ItemChange.id))),
                "feedback": list(self.db.scalars(select(ContentFeedback.id).where(ContentFeedback.item_id == target.id).order_by(ContentFeedback.id))),
            }
        elif entity_type == "topic":
            value = {
                "id": target.id, "name": target.name, "normalized": target.normalized_name, "description": target.description,
                "states": [target.is_followed, target.is_pinned, target.is_muted], "merged": target.merged_into_id,
                "aliases": list(self.db.execute(select(TopicAlias.normalized_name, TopicAlias.name).where(TopicAlias.topic_id == target.id).order_by(TopicAlias.id))),
                "items": list(self.db.scalars(select(ItemTopic.item_id).where(ItemTopic.topic_id == target.id).order_by(ItemTopic.item_id))),
            }
        elif entity_type == "preference":
            value = {"id": target.id, "scope": target.scope, "effect": target.effect, "value": target.value, "kind": target.kind, "note": target.note, "active": target.active}
        elif entity_type == "briefing":
            value = {
                "id": target.id, "subscription": target.subscription_id, "title": target.title, "kind": target.kind,
                "content": target.content, "itemCount": target.item_count, "period": [_iso(target.period_start), _iso(target.period_end)],
                "series": target.series_id, "version": target.version_number, "previous": target.previous_version_id,
                "citation": [target.citation_status, target.citation_warnings_json],
                "publications": list(self.db.scalars(select(HermesPublication.id).where(HermesPublication.briefing_id == target.id).order_by(HermesPublication.id))),
                "feedback": list(self.db.scalars(select(ContentFeedback.id).where(ContentFeedback.briefing_id == target.id).order_by(ContentFeedback.id))),
            }
        elif entity_type == "publication":
            value = {
                "id": target.id, "key": target.idempotency_key, "hash": target.payload_hash, "subscription": target.subscription_id,
                "briefing": target.briefing_id, "origin": target.origin, "topic": target.topic, "request": target.request_summary,
                "items": list(self.db.execute(select(PublicationItem.item_id, PublicationItem.ordinal, PublicationItem.was_inserted).where(PublicationItem.publication_id == target.id).order_by(PublicationItem.ordinal))),
            }
        elif entity_type == "item_tag":
            value = {"key": target_key, "created": _iso(target.created_at)}
        elif entity_type == "item_topic":
            value = {"key": target_key, "source": target.source, "confidence": target.confidence}
        else:
            raise RuntimeError(f"未知迁移记录类型：{entity_type}")
        return _json_hash(value)

    @staticmethod
    def _batch_dict(batch: ImportBatch) -> dict[str, Any]:
        return {
            "id": batch.id,
            "payloadHash": batch.payload_hash,
            "schemaVersion": batch.schema_version,
            "reportConflict": batch.report_conflict,
            "status": batch.status,
            "counts": json.loads(batch.counts_json or "{}"),
            "summary": json.loads(batch.summary_json or "{}"),
            "createdAt": _iso(batch.created_at),
            "undoneAt": _iso(batch.undone_at),
        }
