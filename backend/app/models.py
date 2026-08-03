from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_saved: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ignored: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    subscription: Mapped[Subscription] = relationship(back_populates="items")
    publication_links: Mapped[list["PublicationItem"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
    )


class Briefing(Base):
    __tablename__ = "briefings"

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30), index=True)
    content: Mapped[str] = mapped_column(Text)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    subscription: Mapped[Subscription] = relationship(back_populates="briefings")


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
    topic: Mapped[str] = mapped_column(String(200))
    request_summary: Mapped[str] = mapped_column(String(1000))
    origin: Mapped[str] = mapped_column(String(40), default="weixin-hermes")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    item_links: Mapped[list["PublicationItem"]] = relationship(
        back_populates="publication",
        cascade="all, delete-orphan",
        order_by="PublicationItem.ordinal",
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

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    hermes_run_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)

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

