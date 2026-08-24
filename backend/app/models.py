import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(30), index=True)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    schedule: Mapped[str] = mapped_column(String(80))
    prompt: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    items: Mapped[list["IntelligenceItem"]] = relationship(back_populates="subscription")
    briefings: Mapped[list["Briefing"]] = relationship(back_populates="subscription")
    runs: Mapped[list["TaskRun"]] = relationship(back_populates="subscription")


class IntelligenceItem(Base):
    __tablename__ = "intelligence_items"
    __table_args__ = (
        Index(
            "ix_intelligence_items_feed_default",
            "is_invalid",
            "merged_into_id",
            "importance",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(120))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    reason: Mapped[str] = mapped_column(Text, default="")
    importance: Mapped[float] = mapped_column(Float, default=0)
    personalized_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    recommendation_reasons_json: Mapped[str] = mapped_column(Text, default="[]")
    personalization_version: Mapped[int] = mapped_column(Integer, default=1)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_saved: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ignored: Mapped[bool] = mapped_column(Boolean, default=False)
    is_invalid: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    source_unavailable: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    latest_change_type: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    merged_into_id: Mapped[int | None] = mapped_column(
        ForeignKey("intelligence_items.id"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    subscription: Mapped[Subscription] = relationship(back_populates="items")
    publication_links: Mapped[list["PublicationItem"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
    )
    revisions: Mapped[list["ItemRevision"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="ItemRevision.created_at.desc()",
    )
    merged_into: Mapped["IntelligenceItem | None"] = relationship(
        remote_side="IntelligenceItem.id",
        foreign_keys=[merged_into_id],
    )
    tags: Mapped[list["ItemTag"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="ItemTag.name",
    )
    topic_links: Mapped[list["ItemTopic"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
    )
    changes: Mapped[list["ItemChange"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        foreign_keys="ItemChange.item_id",
        order_by="ItemChange.detected_at.desc()",
    )


class ItemTag(Base):
    __tablename__ = "item_tags"
    __table_args__ = (Index("ix_item_tags_name_item", "name", "item_id"),)

    item_id: Mapped[int] = mapped_column(
        ForeignKey("intelligence_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    item: Mapped[IntelligenceItem] = relationship(back_populates="tags")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    normalized_name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    is_followed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    aliases: Mapped[list["TopicAlias"]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    item_links: Mapped[list["ItemTopic"]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    merged_into: Mapped["Topic | None"] = relationship(remote_side="Topic.id", foreign_keys=[merged_into_id])


class TopicAlias(Base):
    __tablename__ = "topic_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    normalized_name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(30), default="keyword")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    topic: Mapped[Topic] = relationship(back_populates="aliases")


class ItemTopic(Base):
    __tablename__ = "item_topics"
    __table_args__ = (UniqueConstraint("item_id", "topic_id", name="uq_item_topics_item_topic"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("intelligence_items.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(30), default="keyword")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    item: Mapped[IntelligenceItem] = relationship(back_populates="topic_links")
    topic: Mapped[Topic] = relationship(back_populates="item_links")


class ItemRevision(Base):
    __tablename__ = "item_revisions"
    __table_args__ = (Index("ix_item_revisions_item_created", "item_id", "created_at", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("intelligence_items.id", ondelete="CASCADE"),
        index=True,
    )
    action: Mapped[str] = mapped_column(String(40), index=True)
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    item: Mapped[IntelligenceItem] = relationship(back_populates="revisions")


class ItemChange(Base):
    __tablename__ = "item_changes"
    __table_args__ = (
        Index("ix_item_changes_item_detected", "item_id", "detected_at", "id"),
        Index("ix_item_changes_related_item", "related_item_id", "detected_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("intelligence_items.id", ondelete="CASCADE"), index=True)
    related_item_id: Mapped[int | None] = mapped_column(ForeignKey("intelligence_items.id"), nullable=True)
    task_run_id: Mapped[int | None] = mapped_column(ForeignKey("task_runs.id"), nullable=True, index=True)
    publication_id: Mapped[int | None] = mapped_column(ForeignKey("hermes_publications.id"), nullable=True, index=True)
    change_type: Mapped[str] = mapped_column(String(30), index=True)
    basis: Mapped[str] = mapped_column(Text, default="")
    source_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="confirmed", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    item: Mapped[IntelligenceItem] = relationship(back_populates="changes", foreign_keys=[item_id])
    related_item: Mapped[IntelligenceItem | None] = relationship(foreign_keys=[related_item_id])


class Briefing(Base):
    __tablename__ = "briefings"
    __table_args__ = (
        UniqueConstraint("series_id", "version_number", name="uq_briefings_series_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30), index=True)
    content: Mapped[str] = mapped_column(Text)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    series_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    previous_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("briefings.id"), nullable=True, index=True
    )
    generation_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_runs.id"), nullable=True, index=True
    )
    citation_status: Mapped[str] = mapped_column(String(30), default="unchecked")
    citation_warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    subscription: Mapped[Subscription] = relationship(back_populates="briefings")

    @property
    def citation_warnings(self) -> list[str]:
        try:
            value = json.loads(self.citation_warnings_json)
        except (TypeError, ValueError):
            return []
        return [str(item) for item in value] if isinstance(value, list) else []


class HermesPublication(Base):
    __tablename__ = "hermes_publications"

    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    briefing_id: Mapped[int | None] = mapped_column(ForeignKey("briefings.id"), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    hermes_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    task_run_id: Mapped[int | None] = mapped_column(ForeignKey("task_runs.id"), nullable=True, index=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    filtered_count: Mapped[int] = mapped_column(Integer, default=0)
    topic: Mapped[str] = mapped_column(String(200))
    request_summary: Mapped[str] = mapped_column(String(1000))
    origin: Mapped[str] = mapped_column(String(40), default="weixin-hermes")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    item_links: Mapped[list["PublicationItem"]] = relationship(
        back_populates="publication",
        cascade="all, delete-orphan",
        order_by="PublicationItem.ordinal",
    )
    quality_decisions: Mapped[list["HermesQualityDecision"]] = relationship(
        back_populates="publication",
        cascade="all, delete-orphan",
        order_by="HermesQualityDecision.created_at",
    )


class PublicationItem(Base):
    __tablename__ = "publication_items"
    __table_args__ = (
        UniqueConstraint("publication_id", "item_id", name="uq_publication_items_publication_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    publication_id: Mapped[int] = mapped_column(
        ForeignKey("hermes_publications.id", ondelete="CASCADE"),
        index=True,
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("intelligence_items.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    was_inserted: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    publication: Mapped[HermesPublication] = relationship(back_populates="item_links")
    item: Mapped[IntelligenceItem] = relationship(back_populates="publication_links")


class TaskRun(Base):
    __tablename__ = "task_runs"
    __table_args__ = (
        Index(
            "uq_task_runs_active_retry",
            "retry_of_id",
            unique=True,
            sqlite_where=text("retry_of_id IS NOT NULL AND status IN ('queued', 'running')"),
        ),
        Index(
            "uq_task_runs_active_report_series",
            "report_series_id",
            unique=True,
            sqlite_where=text(
                "origin = 'web-report' AND report_series_id IS NOT NULL "
                "AND status IN ('queued', 'running')"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    retry_of_id: Mapped[int | None] = mapped_column(ForeignKey("task_runs.id"), nullable=True, index=True)
    hermes_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True, index=True)
    origin: Mapped[str] = mapped_column(String(40), default="subscription-hermes")
    topic: Mapped[str | None] = mapped_column(String(200), nullable=True)
    request_summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(40), default="accepted")
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_item_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_series_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    report_version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    subscription: Mapped[Subscription] = relationship(back_populates="runs")


class HermesIntegration(Base):
    __tablename__ = "hermes_integrations"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_hint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_status: Mapped[str] = mapped_column(String(32), default="unconfigured")
    last_message: Mapped[str] = mapped_column(String(500), default="尚未配置Hermes连接")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hermes_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class HermesPreference(Base):
    __tablename__ = "hermes_preferences"
    __table_args__ = (
        UniqueConstraint("scope", "effect", "value", "kind", name="uq_hermes_preferences_rule"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(30), index=True)
    effect: Mapped[str] = mapped_column(String(30), index=True)
    value: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30), default="all", index=True)
    note: Mapped[str] = mapped_column(String(1000), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class PersonalizationSettings(Base):
    __tablename__ = "personalization_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    auto_learning_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    algorithm_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class SavedView(Base):
    __tablename__ = "saved_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    query_string: Mapped[str] = mapped_column(String(1500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ItemBulkOperation(Base):
    __tablename__ = "item_bulk_operations"

    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class HermesQualityDecision(Base):
    __tablename__ = "hermes_quality_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    publication_id: Mapped[int] = mapped_column(
        ForeignKey("hermes_publications.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[int | None] = mapped_column(ForeignKey("intelligence_items.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(30), index=True)
    reason_code: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(120))
    keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    importance: Mapped[float] = mapped_column(Float, default=0)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    publication: Mapped[HermesPublication] = relationship(back_populates="quality_decisions")
