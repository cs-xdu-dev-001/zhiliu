import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from app.models import Briefing, IntelligenceItem


STOP_PHRASES = (
    "请帮我",
    "帮我",
    "请",
    "找出",
    "查找",
    "搜索",
    "最近",
    "过去",
    "有哪些",
    "关于",
    "值得关注的",
    "知流里的",
    "知流中",
    "知流",
)


@dataclass
class SearchHit:
    result_type: str
    result_id: int
    kind: str
    title: str
    summary: str
    source: str | None
    source_url: str | None
    item_count: int | None
    created_at: datetime


@dataclass
class SearchBundle:
    query: str
    items: list[SearchHit]
    briefings: list[SearchHit]
    item_total: int
    briefing_total: int


def _terms(query: str) -> list[str]:
    cleaned = query.strip().casefold()
    for phrase in STOP_PHRASES:
        cleaned = cleaned.replace(phrase, " ")
    chunks = re.findall(r"[a-z0-9][a-z0-9_.+#-]*|[\u3400-\u9fff]{2,}", cleaned)
    return list(dict.fromkeys(chunk for chunk in chunks if len(chunk) >= 2))[:12]


def _fts_expression(terms: list[str]) -> str | None:
    tokens: list[str] = []
    for term in terms:
        escaped = term.replace('"', '""')
        if re.fullmatch(r"[\u3400-\u9fff]+", term) and len(term) > 6:
            tokens.extend(f'"{escaped[index:index + 3]}"' for index in range(len(term) - 2))
        elif len(term) >= 3:
            tokens.append(f'"{escaped}"')
    return " OR ".join(dict.fromkeys(tokens)) or None


def _summary(value: str, limit: int = 320) -> str:
    normalized = " ".join(value.split())
    return f"{normalized[:limit]}…" if len(normalized) > limit else normalized


class SearchService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def search(
        self,
        query: str,
        *,
        kind: str | None = None,
        days: int | None = None,
        limit: int = 10,
    ) -> SearchBundle:
        normalized = query.strip()[:200]
        terms = _terms(normalized)
        expression = _fts_expression(terms)
        if expression:
            try:
                return self._search_fts(normalized, expression, kind=kind, days=days, limit=limit)
            except DatabaseError:
                self.db.rollback()
        return self._search_fallback(normalized, terms or [normalized], kind=kind, days=days, limit=limit)

    def _search_fts(
        self,
        query: str,
        expression: str,
        *,
        kind: str | None,
        days: int | None,
        limit: int,
    ) -> SearchBundle:
        since = datetime.now(timezone.utc) - timedelta(days=days) if days else None
        item_filters = ["i.is_invalid = 0", "i.merged_into_id IS NULL"]
        briefing_filters: list[str] = []
        params: dict[str, object] = {"expression": expression, "limit": limit}
        if kind:
            item_filters.append("i.kind = :kind")
            briefing_filters.append("b.kind = :kind")
            params["kind"] = kind
        if since:
            item_filters.append("i.created_at >= :since")
            briefing_filters.append("b.created_at >= :since")
            params["since"] = since
        item_where = " AND ".join(item_filters)
        briefing_where = " AND ".join(briefing_filters) or "1 = 1"
        item_rows = self.db.execute(
            text(
                "SELECT i.* FROM intelligence_items_fts "
                "JOIN intelligence_items i ON i.id = intelligence_items_fts.rowid "
                f"WHERE intelligence_items_fts MATCH :expression AND {item_where} "
                "ORDER BY bm25(intelligence_items_fts), i.created_at DESC LIMIT :limit"
            ),
            params,
        ).mappings().all()
        briefing_rows = self.db.execute(
            text(
                "SELECT b.* FROM briefings_fts "
                "JOIN briefings b ON b.id = briefings_fts.rowid "
                f"WHERE briefings_fts MATCH :expression AND {briefing_where} "
                "ORDER BY bm25(briefings_fts), b.created_at DESC LIMIT :limit"
            ),
            params,
        ).mappings().all()
        item_total = self.db.execute(
            text(
                "SELECT count(*) FROM intelligence_items_fts "
                "JOIN intelligence_items i ON i.id = intelligence_items_fts.rowid "
                f"WHERE intelligence_items_fts MATCH :expression AND {item_where}"
            ),
            params,
        ).scalar_one()
        briefing_total = self.db.execute(
            text(
                "SELECT count(*) FROM briefings_fts "
                "JOIN briefings b ON b.id = briefings_fts.rowid "
                f"WHERE briefings_fts MATCH :expression AND {briefing_where}"
            ),
            params,
        ).scalar_one()
        return SearchBundle(
            query=query,
            items=[self._item_hit(row) for row in item_rows],
            briefings=[self._briefing_hit(row) for row in briefing_rows],
            item_total=item_total,
            briefing_total=briefing_total,
        )

    def _search_fallback(
        self,
        query: str,
        terms: list[str],
        *,
        kind: str | None,
        days: int | None,
        limit: int,
    ) -> SearchBundle:
        item_filters = [IntelligenceItem.is_invalid.is_(False), IntelligenceItem.merged_into_id.is_(None)]
        briefing_filters = []
        if kind:
            item_filters.append(IntelligenceItem.kind == kind)
            briefing_filters.append(Briefing.kind == kind)
        if days:
            since = datetime.now(timezone.utc) - timedelta(days=days)
            item_filters.append(IntelligenceItem.created_at >= since)
            briefing_filters.append(Briefing.created_at >= since)
        item_search = []
        briefing_search = []
        for term in terms:
            escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            item_search.extend(
                column.ilike(pattern, escape="\\")
                for column in (
                    IntelligenceItem.title,
                    IntelligenceItem.summary,
                    IntelligenceItem.source,
                    IntelligenceItem.keywords_json,
                    IntelligenceItem.reason,
                )
            )
            briefing_search.extend(
                column.ilike(pattern, escape="\\") for column in (Briefing.title, Briefing.content)
            )
        if item_search:
            item_filters.append(or_(*item_search))
        if briefing_search:
            briefing_filters.append(or_(*briefing_search))
        items = self.db.scalars(
            select(IntelligenceItem)
            .where(*item_filters)
            .order_by(IntelligenceItem.importance.desc(), IntelligenceItem.created_at.desc())
            .limit(limit)
        ).all()
        briefings = self.db.scalars(
            select(Briefing)
            .where(*briefing_filters)
            .order_by(Briefing.created_at.desc())
            .limit(limit)
        ).all()
        item_total = self.db.scalar(select(func.count()).select_from(IntelligenceItem).where(*item_filters)) or 0
        briefing_total = self.db.scalar(select(func.count()).select_from(Briefing).where(*briefing_filters)) or 0
        return SearchBundle(
            query=query,
            items=[self._item_hit(record.__dict__) for record in items],
            briefings=[self._briefing_hit(record.__dict__) for record in briefings],
            item_total=item_total,
            briefing_total=briefing_total,
        )

    @staticmethod
    def _item_hit(row: object) -> SearchHit:
        return SearchHit(
            result_type="item",
            result_id=row["id"],
            kind=row["kind"],
            title=row["title"],
            summary=_summary(row["summary"] or row["reason"] or "暂无摘要"),
            source=row["source"],
            source_url=row["url"],
            item_count=None,
            created_at=row["created_at"],
        )

    @staticmethod
    def _briefing_hit(row: object) -> SearchHit:
        return SearchHit(
            result_type="briefing",
            result_id=row["id"],
            kind=row["kind"],
            title=row["title"],
            summary=_summary(row["content"] or "暂无摘要"),
            source=None,
            source_url=None,
            item_count=row["item_count"],
            created_at=row["created_at"],
        )
