from datetime import datetime
from typing import Literal

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator
from pydantic.alias_generators import to_camel


IntelligenceKind = Literal["news", "paper", "job"]


class McpModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        str_strip_whitespace=True,
        extra="forbid",
    )


class PublishItem(McpModel):
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=5000)
    url: HttpUrl
    source: str = Field(min_length=1, max_length=100)
    published_at: datetime | None = None
    keywords: list[str] = Field(default_factory=list, max_length=20)
    reason: str = Field(default="", max_length=2000)
    importance: float = Field(ge=0, le=1)

    @field_validator("url")
    @classmethod
    def limit_url(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme not in {"http", "https"} or len(str(value)) > 1000:
            raise ValueError("url必须是长度不超过1000的HTTP或HTTPS地址")
        return value

    @field_validator("keywords")
    @classmethod
    def clean_keywords(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if any(len(item) > 80 for item in cleaned):
            raise ValueError("单个关键词不能超过80字符")
        return cleaned


class PublishBriefing(McpModel):
    title: str = Field(min_length=1, max_length=280)
    content: str = Field(min_length=1, max_length=50000)
    period_start: datetime | None = None
    period_end: datetime | None = None


class PublishPayload(McpModel):
    idempotency_key: str = Field(min_length=8, max_length=160)
    trace_id: str = Field(min_length=8, max_length=160)
    hermes_run_id: str | None = Field(default=None, max_length=255)
    topic: str = Field(min_length=1, max_length=200)
    kind: IntelligenceKind
    request_summary: str = Field(min_length=1, max_length=1000)
    items: list[PublishItem] = Field(default_factory=list, max_length=20)
    briefing: PublishBriefing | None = None

    @model_validator(mode="after")
    def require_content(self) -> "PublishPayload":
        if not self.items and self.briefing is None:
            raise ValueError("items与briefing至少提供一个")
        return self


class PublishReceipt(McpModel):
    receipt_id: int
    trace_id: str
    item_count: int
    skipped_count: int
    filtered_count: int = 0
    briefing_id: int | None
    task_run_id: int | None
    message: str
    trace_url: str | None = None
    task_url: str | None = None
    briefing_url: str | None = None
    created_at: datetime
    duplicate: bool = False


class TaskStartPayload(McpModel):
    trace_id: str = Field(min_length=8, max_length=160)
    hermes_run_id: str | None = Field(default=None, max_length=255)
    topic: str = Field(min_length=1, max_length=200)
    kind: IntelligenceKind
    request_summary: str = Field(min_length=1, max_length=1000)


class TaskFailurePayload(McpModel):
    trace_id: str = Field(min_length=8, max_length=160)
    hermes_run_id: str | None = Field(default=None, max_length=255)
    error_message: str = Field(min_length=1, max_length=1000)


class TaskFeedbackReceipt(McpModel):
    task_run_id: int
    trace_id: str
    status: Literal["running", "success", "failed"]
    stage: Literal["processing", "completed", "failed"]
    message: str
    task_url: str | None = None
    duplicate: bool = False


PreferenceScope = Literal["source", "topic", "output"]
PreferenceEffect = Literal["prefer", "avoid", "instruct"]
PreferenceKind = Literal["all", "news", "paper", "job"]
FeedbackPriority = Literal["lower", "normal", "higher"]


class PreferencePayload(McpModel):
    scope: PreferenceScope
    effect: PreferenceEffect
    value: str = Field(min_length=1, max_length=300)
    kind: PreferenceKind = "all"
    note: str = Field(default="", max_length=1000)


class PreferenceReceipt(PreferencePayload):
    preference_id: int
    active: bool
    created: bool = False
    message: str = ""


class PreferenceListReceipt(McpModel):
    preferences: list[PreferenceReceipt]


class PreferenceRemoveReceipt(McpModel):
    preference_id: int
    removed: bool
    message: str


class SearchResult(McpModel):
    result_type: Literal["item", "briefing"]
    result_id: int
    kind: IntelligenceKind
    title: str
    summary: str
    source: str | None = None
    source_url: str | None = None
    detail_url: str | None = None
    created_at: datetime


class SearchPayload(McpModel):
    query: str = Field(min_length=2, max_length=200)
    kind: IntelligenceKind | None = None
    days: int | None = Field(default=None, ge=1, le=3650)
    limit: int = Field(default=10, ge=1, le=20)


class SearchReceipt(McpModel):
    query: str
    results: list[SearchResult]


class ItemFeedbackPayload(McpModel):
    item_id: int = Field(gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    summary: str | None = Field(default=None, min_length=1, max_length=5000)
    kind: IntelligenceKind | None = None
    priority: FeedbackPriority | None = None
    ignored: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> "ItemFeedbackPayload":
        if all(
            value is None
            for value in (self.title, self.summary, self.kind, self.priority, self.ignored)
        ):
            raise ValueError("至少提供一项情报修改")
        return self


class ItemFeedbackReceipt(McpModel):
    item_id: int
    title: str
    importance: float
    ignored: bool
    message: str
    detail_url: str | None = None


class MonitorPayload(McpModel):
    name: str = Field(min_length=1, max_length=120)
    kind: IntelligenceKind
    keywords: list[str] = Field(default_factory=list, max_length=30)
    schedule: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=10000)

    @field_validator("schedule")
    @classmethod
    def valid_schedule(cls, value: str) -> str:
        if not croniter.is_valid(value):
            raise ValueError("请使用标准Cron表达式")
        return value

    @field_validator("keywords")
    @classmethod
    def clean_keywords(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if any(len(item) > 80 for item in cleaned):
            raise ValueError("单个关键词不能超过80字符")
        return cleaned


class MonitorReceipt(McpModel):
    subscription_id: int
    created: bool
