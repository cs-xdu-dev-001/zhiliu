from datetime import datetime
from typing import Literal

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

class HermesConnectionUpdate(ApiModel):
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=500)

class HermesConnectionResponse(ApiModel):
    base_url: str | None = None
    api_key_configured: bool = False
    api_key_hint: str | None = None
    status: Literal["unconfigured", "unreachable", "unauthorized", "connected", "error"] = "unconfigured"
    message: str = ""
    checked_at: datetime | None = None
    version: str | None = None


IntelligenceKind = Literal["news", "paper", "job"]


class SubscriptionPayload(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    kind: IntelligenceKind
    keywords: list[str] = Field(default_factory=list, max_length=30)
    schedule: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=10000)
    enabled: bool = True

    @field_validator("schedule")
    @classmethod
    def validate_schedule(cls, value: str) -> str:
        if not croniter.is_valid(value):
            raise ValueError("请使用标准Cron表达式")
        return value

    @field_validator("keywords")
    @classmethod
    def clean_keywords(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(keyword.strip() for keyword in value if keyword.strip()))


class SubscriptionResponse(SubscriptionPayload):
    id: int
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ItemStateUpdate(ApiModel):
    is_read: bool | None = None
    is_saved: bool | None = None
    is_ignored: bool | None = None


class IntelligenceItemResponse(ApiModel):
    id: int
    subscription_id: int
    kind: IntelligenceKind
    title: str
    summary: str
    url: str
    source: str
    published_at: datetime | None
    keywords: list[str]
    reason: str
    importance: float
    is_read: bool
    is_saved: bool
    is_ignored: bool
    created_at: datetime


class PublicationRecordResponse(ApiModel):
    id: int
    trace_id: str | None
    origin: str
    request_summary: str
    created_at: datetime
    hermes_run_id: str | None
    task_run_id: int | None
    was_inserted: bool
    ordinal: int
    briefing_id: int | None = None
    briefing_title: str | None = None


class ItemDetailResponse(IntelligenceItemResponse):
    publications: list[PublicationRecordResponse]
    trace_available: bool


class ItemPage(ApiModel):
    items: list[IntelligenceItemResponse]
    total: int
    limit: int
    offset: int


class BriefingResponse(ApiModel):
    id: int
    subscription_id: int
    title: str
    kind: IntelligenceKind
    content: str
    item_count: int
    period_start: datetime | None
    period_end: datetime | None
    created_at: datetime


class PublicationSummaryResponse(ApiModel):
    id: int
    trace_id: str | None
    origin: str
    request_summary: str
    created_at: datetime
    hermes_run_id: str | None
    task_run_id: int | None


class SourceItemResponse(ApiModel):
    id: int
    title: str
    summary: str
    source: str
    url: str
    ordinal: int
    was_inserted: bool


class BriefingDetailResponse(BriefingResponse):
    source_items: list[SourceItemResponse]
    publication: PublicationSummaryResponse | None
    trace_available: bool


class TraceSubscriptionResponse(ApiModel):
    id: int
    name: str


class TraceTaskRunResponse(ApiModel):
    id: int
    status: str
    started_at: datetime
    finished_at: datetime | None


class TraceBriefingResponse(ApiModel):
    id: int
    title: str
    kind: IntelligenceKind


class PublicationTraceResponse(ApiModel):
    publication_id: int
    trace_id: str | None
    origin: str
    request_summary: str
    hermes_run_id: str | None
    created_at: datetime
    item_count: int
    skipped_count: int
    subscription: TraceSubscriptionResponse
    task_run: TraceTaskRunResponse | None
    items: list[SourceItemResponse]
    briefing: TraceBriefingResponse | None


class BriefingPage(ApiModel):
    items: list[BriefingResponse]
    total: int
    limit: int
    offset: int


class DashboardResponse(ApiModel):
    unread_count: int
    saved_count: int
    active_subscriptions: int
    failed_runs: int
    top_items: list[IntelligenceItemResponse]
    latest_briefing: BriefingResponse | None


class TaskRunResponse(ApiModel):
    id: int
    subscription_id: int
    hermes_run_id: str | None
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    error_message: str | None


class TaskRunPage(ApiModel):
    items: list[TaskRunResponse]
    total: int
    limit: int
    offset: int

