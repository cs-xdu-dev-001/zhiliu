# 微信Hermes写入知流MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让Hermes在微信对话中自主判断何时把一次性整理结果或长期监测意图写入知流，并由知流现有情报、报告和订阅页面直接展示。

**Architecture:** 在现有FastAPI进程中挂载官方MCP Python SDK 1.x的无状态Streamable HTTP应用，只给MCP子应用增加独立静态Bearer鉴权。`PublicationService`负责校验后的原子入库、分类、来源标记和双层幂等，`MonitorService`复用现有Subscription与scheduler；Hermes通过原生MCP配置发现两个工具，并由一个简短skill约束自然语言触发边界。

**Tech Stack:** Python 3.12+、FastAPI、SQLAlchemy 2、SQLite、Pydantic 2、MCP Python SDK 1.28.x、pytest、React、Vitest、Nginx、Hermes Agent MCP/skills

---

## 文件结构

- `backend/app/mcp_server/schemas.py`：MCP输入、输出schema和规范化校验。
- `backend/app/mcp_server/auth.py`：仅包裹MCP子应用的静态Bearer ASGI鉴权。
- `backend/app/mcp_server/service.py`：一次性发布、幂等、事务和长期监测创建。
- `backend/app/mcp_server/server.py`：注册两个FastMCP工具并构造可挂载ASGI应用。
- `backend/app/models.py`：新增发布回执`HermesPublication`，不改已有表列。
- `backend/app/main.py`：把MCP session manager纳入现有lifespan并挂载`/api/mcp`。
- `backend/tests/test_mcp_*.py`：schema、服务、鉴权和官方客户端集成测试。
- `deploy/hermes/mcp-zhiliu.yaml.example`：可合并进Hermes配置的MCP片段。
- `deploy/hermes/skills/zhiliu-publisher/SKILL.md`：让Hermes按语义决定发布或创建监测。
- `deploy/nginx.conf`：为Streamable HTTP保留Authorization并关闭代理缓冲。
- `README.md`、`.env.example`、`docker-compose.yml`：部署、密钥、安装和验收步骤。

### Task 1: 锁定MCP依赖并增加生产密钥约束

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Modify: `backend/app/core/config.py`
- Modify: `backend/tests/test_config.py`

- [ ] **Step 1: 写生产环境拒绝缺失、示例和短MCP token的失败测试**

在`backend/tests/test_config.py`补充：

```python
@pytest.mark.parametrize(
    "zhiliu_mcp_token",
    [
        "",
        "development-zhiliu-mcp-token-change-me",
        "replace-with-separate-32-character-random-token",
        "too-short",
    ],
)
def test_production_rejects_invalid_mcp_token(zhiliu_mcp_token: str) -> None:
    with pytest.raises(ValidationError, match="ZHILIU_MCP_TOKEN"):
        Settings(
            app_env="production",
            integration_secret_key="production-integration-secret-that-is-long-enough",
            zhiliu_mcp_token=zhiliu_mcp_token,
            _env_file=None,
        )
```

并给`test_production_accepts_explicit_secrets`增加：

```python
zhiliu_mcp_token="production-mcp-token-that-is-long-enough",
```

- [ ] **Step 2: 运行测试并确认因字段不存在而失败**

Run:

```powershell
Set-Location backend
uv run pytest tests/test_config.py -v
```

Expected: `test_production_rejects_invalid_mcp_token`失败，默认/显式token尚未被校验。

- [ ] **Step 3: 实现配置字段与生产校验**

在`Settings`中增加：

```python
zhiliu_mcp_token: str = "development-zhiliu-mcp-token-change-me"
```

把生产校验扩展为：

```python
invalid_mcp_tokens = {
    "development-zhiliu-mcp-token-change-me",
    "replace-with-separate-32-character-random-token",
}
if self.zhiliu_mcp_token in invalid_mcp_tokens or len(self.zhiliu_mcp_token) < 32:
    raise ValueError("ZHILIU_MCP_TOKEN必须替换为至少32位的独立随机值")
```

- [ ] **Step 4: 安装稳定MCP SDK并更新锁文件**

Run:

```powershell
Set-Location backend
uv add "mcp>=1.28.1,<2"
```

Expected: `backend/pyproject.toml`出现`mcp>=1.28.1,<2`，`backend/uv.lock`锁定1.x稳定版本，不选择2.x预发布版。

- [ ] **Step 5: 运行配置测试与依赖导入检查**

Run:

```powershell
uv run pytest tests/test_config.py -v
uv run python -c "from mcp.server.fastmcp import FastMCP; print(FastMCP.__name__)"
```

Expected: 配置测试全部通过，第二条输出`FastMCP`。

- [ ] **Step 6: 提交依赖和配置**

```powershell
git add backend/pyproject.toml backend/uv.lock backend/app/core/config.py backend/tests/test_config.py
git commit -m "build: add stable MCP server dependency"
```

### Task 2: 定义发布schema和发布回执表

**Files:**
- Create: `backend/app/mcp_server/__init__.py`
- Create: `backend/app/mcp_server/schemas.py`
- Modify: `backend/app/models.py`
- Create: `backend/tests/test_mcp_schemas.py`
- Create: `backend/tests/test_mcp_models.py`

- [ ] **Step 1: 写schema边界失败测试**

创建`backend/tests/test_mcp_schemas.py`：

```python
import pytest
from pydantic import ValidationError

from app.mcp_server.schemas import PublishPayload


def valid_payload() -> dict:
    return {
        "idempotencyKey": "wx-20260802-agent-news",
        "topic": "Agent新闻",
        "kind": "news",
        "requestSummary": "整理并保存今天的重要Agent新闻",
        "items": [{
            "title": "Agent框架发布新版本",
            "summary": "新版本改进了工具调用。",
            "url": "https://example.com/release",
            "source": "Example",
            "keywords": ["Agent"],
            "reason": "与关注方向相关",
            "importance": 0.9,
        }],
    }


def test_publish_requires_items_or_briefing() -> None:
    payload = valid_payload()
    payload.pop("items")
    with pytest.raises(ValidationError, match="items与briefing至少提供一个"):
        PublishPayload.model_validate(payload)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", "not-a-url"])
def test_publish_rejects_non_http_source(url: str) -> None:
    payload = valid_payload()
    payload["items"][0]["url"] = url
    with pytest.raises(ValidationError):
        PublishPayload.model_validate(payload)


def test_publish_rejects_more_than_twenty_items() -> None:
    payload = valid_payload()
    payload["items"] = payload["items"] * 21
    with pytest.raises(ValidationError):
        PublishPayload.model_validate(payload)


def test_publish_accepts_camel_case_and_normalizes_keywords() -> None:
    payload = valid_payload()
    payload["items"][0]["keywords"] = [" Agent ", "Agent", "RAG"]
    parsed = PublishPayload.model_validate(payload)
    assert parsed.request_summary == "整理并保存今天的重要Agent新闻"
    assert parsed.items[0].keywords == ["Agent", "RAG"]
```

- [ ] **Step 2: 写回执唯一约束失败测试**

创建`backend/tests/test_mcp_models.py`：

```python
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import HermesPublication, Subscription


def test_publication_keys_are_unique(db_session: Session) -> None:
    subscription = Subscription(
        name="微信整理·情报",
        kind="news",
        keywords_json="[]",
        schedule="0 0 1 1 *",
        prompt="系统分类",
        enabled=False,
    )
    db_session.add(subscription)
    db_session.flush()
    db_session.add(HermesPublication(
        idempotency_key="same-key",
        payload_hash="a" * 64,
        subscription_id=subscription.id,
        item_count=0,
        skipped_count=0,
        topic="主题",
        request_summary="整理主题",
    ))
    db_session.commit()
    db_session.add(HermesPublication(
        idempotency_key="same-key",
        payload_hash="b" * 64,
        subscription_id=subscription.id,
        item_count=0,
        skipped_count=0,
        topic="另一个主题",
        request_summary="整理另一个主题",
    ))
    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 3: 运行测试并确认导入失败**

Run:

```powershell
Set-Location backend
uv run pytest tests/test_mcp_schemas.py tests/test_mcp_models.py -v
```

Expected: FAIL，`app.mcp_server.schemas`和`HermesPublication`尚不存在。

- [ ] **Step 4: 实现严格的MCP schema**

创建空的`backend/app/mcp_server/__init__.py`，并创建`schemas.py`，定义以下完整接口：

```python
from datetime import datetime
from typing import Literal

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator
from pydantic.alias_generators import to_camel

IntelligenceKind = Literal["news", "paper", "job"]


class McpModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel, str_strip_whitespace=True)


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
    item_count: int
    skipped_count: int
    briefing_id: int | None
    created_at: datetime
    duplicate: bool = False


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
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


class MonitorReceipt(McpModel):
    subscription_id: int
    created: bool
```

- [ ] **Step 5: 实现只新增表的发布回执模型**

在`backend/app/models.py`新增：

```python
class HermesPublication(Base):
    __tablename__ = "hermes_publications"

    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    briefing_id: Mapped[int | None] = mapped_column(ForeignKey("briefings.id"), nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    topic: Mapped[str] = mapped_column(String(200))
    request_summary: Mapped[str] = mapped_column(String(1000))
    origin: Mapped[str] = mapped_column(String(40), default="weixin-hermes")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
```

- [ ] **Step 6: 运行schema和模型测试**

Run:

```powershell
uv run pytest tests/test_mcp_schemas.py tests/test_mcp_models.py -v
```

Expected: 全部PASS。

- [ ] **Step 7: 提交schema和模型**

```powershell
git add backend/app/mcp_server backend/app/models.py backend/tests/test_mcp_schemas.py backend/tests/test_mcp_models.py
git commit -m "feat: define Zhiliu MCP publication contracts"
```

### Task 3: 实现一次性发布、分类与幂等事务

**Files:**
- Create: `backend/app/mcp_server/service.py`
- Create: `backend/tests/test_mcp_publication_service.py`

- [ ] **Step 1: 写一次发布同时生成情报、简报和回执的失败测试**

创建`backend/tests/test_mcp_publication_service.py`，提供`publish_payload()`工厂，并覆盖主路径：

```python
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.mcp_server.schemas import PublishPayload
from app.mcp_server.service import PublicationService
from app.models import Briefing, HermesPublication, IntelligenceItem, Subscription


def publish_payload(**changes) -> PublishPayload:
    data = {
        "idempotencyKey": "wx-agent-20260802",
        "topic": "Agent更新",
        "kind": "news",
        "requestSummary": "整理后放进知流",
        "items": [{
            "title": "Agent框架更新",
            "summary": "工具调用能力提升。",
            "url": "https://example.com/agent/",
            "source": "Example",
            "keywords": ["Agent"],
            "reason": "值得关注",
            "importance": 0.9,
        }],
        "briefing": {"title": "Agent更新简报", "content": "本次更新集中在工具调用。"},
    }
    data.update(changes)
    return PublishPayload.model_validate(data)


def test_publish_persists_visible_content_atomically(db_session: Session) -> None:
    receipt = PublicationService(db_session).publish(publish_payload())
    item = db_session.scalar(select(IntelligenceItem))
    briefing = db_session.scalar(select(Briefing))
    category = db_session.get(Subscription, item.subscription_id)

    assert receipt.item_count == 1
    assert receipt.briefing_id == briefing.id
    assert item.source == "Example · 微信Hermes"
    assert item.url == "https://example.com/agent"
    assert briefing.title == "微信整理 · Agent更新简报"
    assert category.name == "微信整理·情报"
    assert category.enabled is False
    assert db_session.scalar(select(func.count()).select_from(HermesPublication)) == 1
```

- [ ] **Step 2: 写双层幂等与冲突失败测试**

在同一文件增加：

```python
import pytest

from app.mcp_server.service import PublicationConflict, PublicationFailure


def test_same_key_and_payload_returns_original_receipt(db_session: Session) -> None:
    service = PublicationService(db_session)
    first = service.publish(publish_payload())
    second = service.publish(publish_payload())
    assert second.receipt_id == first.receipt_id
    assert second.duplicate is True


def test_same_payload_with_new_key_returns_original_receipt(db_session: Session) -> None:
    service = PublicationService(db_session)
    first = service.publish(publish_payload())
    second = service.publish(publish_payload(idempotencyKey="wx-agent-retry-new-key"))
    assert second.receipt_id == first.receipt_id
    assert second.duplicate is True


def test_same_key_with_changed_payload_is_rejected(db_session: Session) -> None:
    service = PublicationService(db_session)
    service.publish(publish_payload())
    with pytest.raises(PublicationConflict, match="幂等键已用于不同内容"):
        service.publish(publish_payload(topic="被修改的主题"))
```

- [ ] **Step 3: 写情报指纹去重和失败回滚测试**

增加：

```python
def test_existing_item_is_counted_as_skipped(db_session: Session) -> None:
    service = PublicationService(db_session)
    first = service.publish(publish_payload(briefing=None))
    second_payload = publish_payload(idempotencyKey="another-publish", topic="另一批", briefing=None)
    second = service.publish(second_payload)
    assert first.item_count == 1
    assert second.item_count == 0
    assert second.skipped_count == 1


def test_failure_rolls_back_items_briefing_and_receipt(db_session: Session, monkeypatch) -> None:
    service = PublicationService(db_session)
    monkeypatch.setattr(service, "_create_receipt", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(PublicationFailure, match="发布失败，未写入知流"):
        service.publish(publish_payload())
    assert db_session.scalar(select(func.count()).select_from(IntelligenceItem)) == 0
    assert db_session.scalar(select(func.count()).select_from(Briefing)) == 0
    assert db_session.scalar(select(func.count()).select_from(HermesPublication)) == 0
```

- [ ] **Step 4: 运行测试并确认服务尚不存在**

Run:

```powershell
Set-Location backend
uv run pytest tests/test_mcp_publication_service.py -v
```

Expected: FAIL，`PublicationService`尚不存在。

- [ ] **Step 5: 实现规范化hash、分类、发布和稳定回执**

在`service.py`实现以下公开接口和常量；`payload_hash`必须排除`idempotency_key`，否则“换key重试”无法命中同一内容：

```python
AUTO_CATEGORIES = {
    "news": "微信整理·情报",
    "paper": "微信整理·论文",
    "job": "微信整理·岗位",
}
AUTO_SCHEDULE = "0 0 1 1 *"
AUTO_PROMPT = "系统分类：保存Hermes微信一次性整理结果，不参与定时执行。"


class PublicationConflict(ValueError):
    pass


class PublicationFailure(RuntimeError):
    pass


def publication_hash(payload: PublishPayload) -> str:
    body = payload.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude={"idempotency_key"},
    )
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class PublicationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def publish(self, payload: PublishPayload) -> PublishReceipt:
        digest = publication_hash(payload)
        by_key = self.db.scalar(select(HermesPublication).where(
            HermesPublication.idempotency_key == payload.idempotency_key
        ))
        if by_key is not None:
            if by_key.payload_hash != digest:
                raise PublicationConflict("幂等键已用于不同内容，请生成新键后重试")
            return self._receipt(by_key, duplicate=True)
        by_hash = self.db.scalar(select(HermesPublication).where(
            HermesPublication.payload_hash == digest
        ))
        if by_hash is not None:
            return self._receipt(by_hash, duplicate=True)

        try:
            subscription = self._get_or_create_category(payload.kind)
            inserted, skipped = self._insert_items(subscription.id, payload)
            briefing = self._insert_briefing(subscription.id, payload, inserted)
            publication = self._create_receipt(
                subscription.id, payload, digest, inserted, skipped, briefing.id if briefing else None
            )
            self.db.commit()
            self.db.refresh(publication)
            return self._receipt(publication, duplicate=False)
        except IntegrityError:
            self.db.rollback()
            existing = self.db.scalar(select(HermesPublication).where(
                (HermesPublication.idempotency_key == payload.idempotency_key)
                | (HermesPublication.payload_hash == digest)
            ))
            if existing is not None and existing.payload_hash == digest:
                return self._receipt(existing, duplicate=True)
            raise PublicationConflict("发布发生并发冲突，未写入知流")
        except Exception:
            self.db.rollback()
            raise PublicationFailure("发布失败，未写入知流") from None
```

`service.py`导入`hashlib`、`json`、`select`、`IntegrityError`、`Session`，以及现有`normalize_url`和`item_fingerprint`。私有方法完整实现为：

```python
def _get_or_create_category(self, kind: str) -> Subscription:
    name = AUTO_CATEGORIES[kind]
    record = self.db.scalar(select(Subscription).where(
        Subscription.name == name,
        Subscription.kind == kind,
        Subscription.prompt == AUTO_PROMPT,
    ))
    if record is None:
        record = Subscription(
            name=name,
            kind=kind,
            keywords_json="[]",
            schedule=AUTO_SCHEDULE,
            prompt=AUTO_PROMPT,
            enabled=False,
        )
        self.db.add(record)
        self.db.flush()
    elif record.enabled:
        record.enabled = False
    return record

def _insert_items(self, subscription_id: int, payload: PublishPayload) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    for item in payload.items:
        normalized_url = normalize_url(str(item.url)).rstrip("/")
        fingerprint = item_fingerprint(item.title, normalized_url)
        existing = self.db.scalar(select(IntelligenceItem.id).where(
            IntelligenceItem.fingerprint == fingerprint
        ))
        if existing is not None:
            skipped += 1
            continue
        source = item.source if item.source.endswith(" · 微信Hermes") else f"{item.source} · 微信Hermes"
        self.db.add(IntelligenceItem(
            subscription_id=subscription_id,
            kind=payload.kind,
            title=item.title,
            summary=item.summary,
            url=normalized_url,
            source=source,
            published_at=item.published_at,
            keywords_json=json.dumps(item.keywords, ensure_ascii=False),
            reason=item.reason,
            importance=item.importance,
            fingerprint=fingerprint,
        ))
        inserted += 1
    return inserted, skipped

def _insert_briefing(
    self, subscription_id: int, payload: PublishPayload, inserted: int
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
        item_count=inserted,
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
    briefing_id: int | None,
) -> HermesPublication:
    publication = HermesPublication(
        idempotency_key=payload.idempotency_key,
        payload_hash=digest,
        subscription_id=subscription_id,
        briefing_id=briefing_id,
        item_count=inserted,
        skipped_count=skipped,
        topic=payload.topic,
        request_summary=payload.request_summary,
        origin="weixin-hermes",
    )
    self.db.add(publication)
    self.db.flush()
    return publication

@staticmethod
def _receipt(publication: HermesPublication, *, duplicate: bool) -> PublishReceipt:
    return PublishReceipt(
        receipt_id=publication.id,
        item_count=publication.item_count,
        skipped_count=publication.skipped_count,
        briefing_id=publication.briefing_id,
        created_at=publication.created_at,
        duplicate=duplicate,
    )
```

以上私有方法均不得自行`commit()`。

- [ ] **Step 6: 运行发布服务测试**

Run:

```powershell
uv run pytest tests/test_mcp_publication_service.py -v
```

Expected: 全部PASS，重复payload不会增加记录，失败路径三个表均为0。

- [ ] **Step 7: 提交发布服务**

```powershell
git add backend/app/mcp_server/service.py backend/tests/test_mcp_publication_service.py
git commit -m "feat: publish Hermes results atomically"
```

### Task 4: 实现长期监测工具的现有订阅复用

**Files:**
- Modify: `backend/app/mcp_server/service.py`
- Create: `backend/tests/test_mcp_monitor_service.py`

- [ ] **Step 1: 写创建和完全重复复用的失败测试**

创建`backend/tests/test_mcp_monitor_service.py`：

```python
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.mcp_server.schemas import MonitorPayload
from app.mcp_server.service import MonitorFailure, MonitorService
from app.models import Subscription


def monitor_payload() -> MonitorPayload:
    return MonitorPayload(
        name="每日Agent动态",
        kind="news",
        keywords=["Agent", "MCP"],
        schedule="0 8 * * *",
        prompt="每天检索Agent和MCP的重要动态并生成简报。",
    )


def test_create_monitor_enables_existing_scheduler_path(db_session: Session) -> None:
    receipt = MonitorService(db_session).create(monitor_payload())
    record = db_session.get(Subscription, receipt.subscription_id)
    assert receipt.created is True
    assert record.enabled is True
    assert record.keywords_json == '["Agent", "MCP"]'


def test_exact_duplicate_monitor_returns_existing(db_session: Session) -> None:
    service = MonitorService(db_session)
    first = service.create(monitor_payload())
    second = service.create(monitor_payload())
    assert second.subscription_id == first.subscription_id
    assert second.created is False
    assert db_session.scalar(select(func.count()).select_from(Subscription)) == 1


def test_monitor_failure_rolls_back_and_hides_database_details(db_session: Session, monkeypatch) -> None:
    monkeypatch.setattr(db_session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("database path leaked")))
    with pytest.raises(MonitorFailure, match="监测创建失败，未写入知流"):
        MonitorService(db_session).create(monitor_payload())
    assert db_session.scalar(select(func.count()).select_from(Subscription)) == 0
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```powershell
Set-Location backend
uv run pytest tests/test_mcp_monitor_service.py -v
```

Expected: FAIL，`MonitorService`尚不存在。

- [ ] **Step 3: 实现MonitorService**

在`service.py`增加：

```python
class MonitorFailure(RuntimeError):
    pass


class MonitorService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, payload: MonitorPayload) -> MonitorReceipt:
        existing = self.db.scalar(select(Subscription).where(
            Subscription.name == payload.name,
            Subscription.kind == payload.kind,
            Subscription.schedule == payload.schedule,
            Subscription.prompt == payload.prompt,
        ))
        if existing is not None:
            return MonitorReceipt(subscription_id=existing.id, created=False)
        record = Subscription(
            name=payload.name,
            kind=payload.kind,
            keywords_json=json.dumps(payload.keywords, ensure_ascii=False),
            schedule=payload.schedule,
            prompt=payload.prompt,
            enabled=True,
        )
        try:
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
        except Exception:
            self.db.rollback()
            raise MonitorFailure("监测创建失败，未写入知流") from None
        return MonitorReceipt(subscription_id=record.id, created=True)
```

不直接调用scheduler私有状态；现有`refresh_subscription_jobs`每60秒读取`enabled=true`订阅并注册Cron任务。

- [ ] **Step 4: 运行监测与现有scheduler测试**

Run:

```powershell
uv run pytest tests/test_mcp_monitor_service.py tests/test_scheduler.py -v
```

Expected: 全部PASS。

- [ ] **Step 5: 提交监测服务**

```powershell
git add backend/app/mcp_server/service.py backend/tests/test_mcp_monitor_service.py
git commit -m "feat: create recurring monitors from Hermes"
```

### Task 5: 挂载带独立Bearer鉴权的MCP工具

**Files:**
- Create: `backend/app/mcp_server/auth.py`
- Create: `backend/app/mcp_server/server.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/test_mcp_auth.py`
- Create: `backend/tests/test_mcp_integration.py`

- [ ] **Step 1: 写缺失和错误Bearer均被拒绝的失败测试**

创建`backend/tests/test_mcp_auth.py`：

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@pytest.mark.asyncio
@pytest.mark.parametrize("authorization", [None, "Bearer wrong-token-that-is-long-enough"])
async def test_mcp_rejects_missing_or_wrong_bearer(authorization: str | None) -> None:
    settings = Settings(
        scheduler_enabled=False,
        zhiliu_mcp_token="test-mcp-token-that-is-at-least-32-characters",
        _env_file=None,
    )
    app = create_app(start_background_scheduler=False, settings=settings)
    headers = {"Authorization": authorization} if authorization else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/mcp", headers=headers, json={})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "test-mcp-token" not in response.text
```

- [ ] **Step 2: 写官方MCP客户端发现并调用两个工具的失败测试**

创建`backend/tests/test_mcp_integration.py`：

```python
from contextlib import nullcontext

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import create_app
from app.models import IntelligenceItem, Subscription


@pytest.mark.asyncio
async def test_official_client_discovers_and_calls_zhiliu_tools(db_session: Session) -> None:
    token = "test-mcp-token-that-is-at-least-32-characters"
    settings = Settings(scheduler_enabled=False, zhiliu_mcp_token=token, _env_file=None)
    app = create_app(
        start_background_scheduler=False,
        settings=settings,
        mcp_session_factory=lambda: nullcontext(db_session),
    )
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {token}"}

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=headers) as http_client:
            async with streamable_http_client("http://test/api/mcp", http_client=http_client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert {tool.name for tool in tools.tools} == {"zhiliu_publish", "zhiliu_create_monitor"}
                    result = await session.call_tool("zhiliu_publish", arguments={
                        "idempotencyKey": "official-client-test",
                        "topic": "MCP测试",
                        "kind": "news",
                        "requestSummary": "保存MCP测试结果",
                        "items": [{
                            "title": "MCP联通",
                            "summary": "官方客户端调用成功。",
                            "url": "https://example.com/mcp",
                            "source": "Example",
                            "keywords": ["MCP"],
                            "reason": "验证链路",
                            "importance": 0.8,
                        }],
                    })
                    assert result.isError is False

    assert db_session.scalar(select(IntelligenceItem).where(IntelligenceItem.title == "MCP联通")) is not None
    category = db_session.scalar(select(Subscription).where(Subscription.name == "微信整理·情报"))
    assert category is not None
```

- [ ] **Step 3: 运行测试并确认挂载和参数尚不存在**

Run:

```powershell
Set-Location backend
uv run pytest tests/test_mcp_auth.py tests/test_mcp_integration.py -v
```

Expected: FAIL，`create_app`尚不接受`settings`/`mcp_session_factory`且`/api/mcp`未挂载。

- [ ] **Step 4: 实现只保护MCP子应用的恒定时间Bearer鉴权**

创建`backend/app/mcp_server/auth.py`：

```python
import secrets
from collections.abc import Awaitable, Callable

ASGIApp = Callable[[dict, Callable[[], Awaitable[dict]], Callable[[dict], Awaitable[None]]], Awaitable[None]]


class StaticBearerAuth:
    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope: dict, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"authorization", b"")
        if not secrets.compare_digest(supplied, self.expected):
            body = b'{"detail":"MCP\xe6\x9c\xaa\xe6\x8e\x88\xe6\x9d\x83"}'
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"www-authenticate", b"Bearer"),
                    (b"content-length", str(len(body)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
```

实现时用`json.dumps({"detail": "MCP未授权"}, ensure_ascii=False).encode()`生成body，避免手写字节转义；上面的响应字段必须保持一致，且不得记录header。

- [ ] **Step 5: 注册两个camelCase参数工具并构造ASGI应用**

创建`backend/app/mcp_server/server.py`，核心接口如下：

```python
from collections.abc import Callable, ContextManager

from mcp.server.fastmcp import FastMCP
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.mcp_server.auth import StaticBearerAuth
from app.mcp_server.schemas import (
    IntelligenceKind, MonitorPayload, MonitorReceipt, PublishBriefing,
    PublishItem, PublishPayload, PublishReceipt,
)
from app.mcp_server.service import MonitorService, PublicationService

SessionFactory = Callable[[], ContextManager[Session]]


def build_mcp_server(session_factory: SessionFactory = SessionLocal) -> FastMCP:
    server = FastMCP(
        "知流",
        instructions="将Hermes已完成的整理结果发布到知流，或创建用户明确要求的长期监测。",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
    )

    @server.tool(name="zhiliu_publish")
    def zhiliu_publish(
        idempotencyKey: str,
        topic: str,
        kind: IntelligenceKind,
        requestSummary: str,
        items: list[PublishItem] | None = None,
        briefing: PublishBriefing | None = None,
    ) -> PublishReceipt:
        payload = PublishPayload.model_validate({
            "idempotencyKey": idempotencyKey,
            "topic": topic,
            "kind": kind,
            "requestSummary": requestSummary,
            "items": items or [],
            "briefing": briefing,
        })
        with session_factory() as db:
            return PublicationService(db).publish(payload)

    @server.tool(name="zhiliu_create_monitor")
    def zhiliu_create_monitor(
        name: str,
        kind: IntelligenceKind,
        keywords: list[str],
        schedule: str,
        prompt: str,
    ) -> MonitorReceipt:
        payload = MonitorPayload(
            name=name, kind=kind, keywords=keywords, schedule=schedule, prompt=prompt
        )
        with session_factory() as db:
            return MonitorService(db).create(payload)

    return server


def build_mcp_asgi(token: str, session_factory: SessionFactory = SessionLocal):
    server = build_mcp_server(session_factory)
    return server, StaticBearerAuth(server.streamable_http_app(), token)
```

- [ ] **Step 6: 将MCP生命周期合并进FastAPI而不影响Web API**

修改`create_app`签名：

```python
def create_app(
    *,
    start_background_scheduler: bool | None = None,
    settings: Settings | None = None,
    mcp_session_factory: SessionFactory = SessionLocal,
) -> FastAPI:
```

函数内使用`settings = settings or get_settings()`，调用`build_mcp_asgi(settings.zhiliu_mcp_token, mcp_session_factory)`。lifespan中把现有初始化包在：

```python
async with mcp_server.session_manager.run():
    if should_start_scheduler:
        start_scheduler()
    yield
    if should_start_scheduler:
        stop_scheduler()
```

注册现有router后增加：

```python
application.mount("/api/mcp", mcp_asgi)
```

保持`/api/health`和所有现有API无鉴权行为不变。

- [ ] **Step 7: 运行MCP与现有API测试**

Run:

```powershell
uv run pytest tests/test_mcp_auth.py tests/test_mcp_integration.py tests/test_health.py tests/test_public_auth_routes.py -v
```

Expected: 全部PASS；官方客户端只发现两个工具并成功落库，普通Web API行为不变。

- [ ] **Step 8: 提交MCP入口**

```powershell
git add backend/app/mcp_server/auth.py backend/app/mcp_server/server.py backend/app/main.py backend/tests/conftest.py backend/tests/test_mcp_auth.py backend/tests/test_mcp_integration.py
git commit -m "feat: expose authenticated Zhiliu MCP tools"
```

### Task 6: 验证现有前端直接呈现微信Hermes内容

**Files:**
- Modify: `frontend/src/components/ItemCard.test.tsx`
- Modify: `frontend/src/pages/Reports.test.tsx`
- Modify: `backend/tests/test_mcp_integration.py`

- [ ] **Step 1: 给情报卡增加来源呈现测试**

在`ItemCard.test.tsx`增加：

```tsx
it("展示微信Hermes组合来源", () => {
  render(<ItemCard item={{ ...item, source: "arXiv · 微信Hermes" }} />);
  expect(screen.getByText("arXiv · 微信Hermes")).toBeVisible();
});
```

- [ ] **Step 2: 给报告页增加微信整理标题测试**

把`Reports.test.tsx`测试数据标题改为`微信整理 · 今日AI热点简报`，并在现有测试中增加：

```tsx
expect(screen.getAllByText("微信整理 · 今日AI热点简报")).toHaveLength(2);
```

列表和详情各显示一次，因此期望数量为2。

- [ ] **Step 3: 验证MCP发布内容可被现有REST读取**

在`test_mcp_integration.py`的工具调用完成后，用同一app增加：

```python
async with httpx.AsyncClient(transport=transport, base_url="http://test") as web_client:
    items_response = await web_client.get("/api/items")
assert items_response.status_code == 200
assert items_response.json()["items"][0]["source"] == "Example · 微信Hermes"
```

- [ ] **Step 4: 运行前后端呈现测试**

Run:

```powershell
Set-Location frontend
npm test -- --run src/components/ItemCard.test.tsx src/pages/Reports.test.tsx
Set-Location ../backend
uv run pytest tests/test_mcp_integration.py -v
```

Expected: 全部PASS，不需要新增前端页面或生产组件。

- [ ] **Step 5: 提交呈现验收**

```powershell
git add frontend/src/components/ItemCard.test.tsx frontend/src/pages/Reports.test.tsx backend/tests/test_mcp_integration.py
git commit -m "test: verify WeChat Hermes content presentation"
```

### Task 7: 提供Hermes MCP配置、自然触发skill和部署配置

**Files:**
- Create: `deploy/hermes/mcp-zhiliu.yaml.example`
- Create: `deploy/hermes/skills/zhiliu-publisher/SKILL.md`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `deploy/nginx.conf`
- Modify: `README.md`

- [ ] **Step 1: 新增独立MCP token配置**

在`.env.example`增加：

```dotenv
# 仅供Hermes调用知流MCP，必须与其他密钥不同。
ZHILIU_MCP_TOKEN=replace-with-separate-32-character-random-token
```

在`docker-compose.yml`的backend环境增加：

```yaml
ZHILIU_MCP_TOKEN: ${ZHILIU_MCP_TOKEN:-replace-with-separate-32-character-random-token}
```

- [ ] **Step 2: 创建可合并而非覆盖的Hermes配置片段**

创建`deploy/hermes/mcp-zhiliu.yaml.example`：

```yaml
mcp_servers:
  zhiliu:
    url: http://127.0.0.1:8080/api/mcp
    headers:
      Authorization: "Bearer ${ZHILIU_MCP_TOKEN}"
    tools:
      include:
        - zhiliu_publish
        - zhiliu_create_monitor
```

README必须明确“合并到现有`~/.hermes/config.yaml`，不要覆盖原文件”。

- [ ] **Step 3: 创建Hermes自然语言决策skill**

创建`deploy/hermes/skills/zhiliu-publisher/SKILL.md`：

```markdown
---
name: zhiliu-publisher
description: 将微信对话中已完成的检索和整理结果写入知流，或按用户明确要求创建长期监测。用户提到知流并要求整理、保存、呈现、持续关注或定期跟踪时使用；普通聊天和仅询问知流概念时不使用。
---

# 写入知流

先完成理解、检索、核验和整理，再决定是否调用知流工具。不要要求固定前缀。

- 用户要求把本次结果整理、保存或呈现在知流时，调用`zhiliu_publish`。
- 用户明确要求持续关注、每天整理或定期监测时，调用`zhiliu_create_monitor`。
- 无法判断用户要一次性整理还是长期监测时，先询问用户。
- 普通聊天、仅解释“知流是什么”或没有写入意图时，不调用知流工具。
- 情报必须保留HTTP(S)原始来源；没有来源的综合判断放进briefing。
- 为一次发布生成稳定`idempotencyKey`；重试同一内容时沿用原键。
- 工具返回成功前，不得声称已经写入知流；失败时明确说明未写入。
- 不向知流发送微信用户ID、群ID、昵称、完整聊天记录或任何密钥。
```

- [ ] **Step 4: 为MCP代理增加专用Nginx规则**

在通用`location /api/`之前增加：

```nginx
location ^~ /api/mcp {
    proxy_pass http://host.docker.internal:8010;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_read_timeout 300s;
}
```

该前缀规则同时覆盖无尾斜杠、尾斜杠和MCP后续子路径；集成测试必须以文档中的无尾斜杠URL通过。

- [ ] **Step 5: 补齐README部署和验收命令**

README新增“微信Hermes写入知流”章节，包含以下可直接执行步骤：

```bash
cd /opt/zhiliu
ZHILIU_TOKEN="$(openssl rand -hex 32)"
printf '\nZHILIU_MCP_TOKEN=%s\n' "$ZHILIU_TOKEN" >> .env
printf '\nZHILIU_MCP_TOKEN=%s\n' "$ZHILIU_TOKEN" >> ~/.hermes/.env
unset ZHILIU_TOKEN
```

随后说明：合并`deploy/hermes/mcp-zhiliu.yaml.example`；复制skill；重建知流backend并重启gateway：

```bash
mkdir -p ~/.hermes/skills/productivity/zhiliu-publisher
cp /opt/zhiliu/deploy/hermes/skills/zhiliu-publisher/SKILL.md ~/.hermes/skills/productivity/zhiliu-publisher/SKILL.md
cd /opt/zhiliu
docker compose up -d --build backend web
hermes gateway restart
hermes mcp test zhiliu
hermes mcp list
hermes skills list
```

明确说明`ZHILIU_MCP_TOKEN`与Hermes`API_SERVER_KEY`用途相反、必须不同；不要输出真实密钥。真实验收消息使用自然语言，例如：“请检索今天最重要的三条Agent动态，整理好以后放进知流。”

- [ ] **Step 6: 验证skill格式、Compose展开和Nginx语法**

Run:

```powershell
python C:\Users\z2986\.codex\skills\.system\skill-creator\scripts\quick_validate.py deploy/hermes/skills/zhiliu-publisher
docker compose --env-file .env.example config --quiet
docker run --rm -v "${PWD}/deploy/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.27-alpine nginx -t
```

Expected: skill校验通过，Compose配置有效，Nginx输出`syntax is ok`和`test is successful`。

- [ ] **Step 7: 提交部署资产**

```powershell
git add .env.example docker-compose.yml deploy/nginx.conf deploy/hermes README.md
git commit -m "docs: add Hermes WeChat publishing deployment"
```

### Task 8: 全量回归、容器冒烟与真实验收交接

**Files:**
- Modify only if a verification failure reveals an in-scope defect.

- [ ] **Step 1: 运行后端全量测试**

Run:

```powershell
Set-Location backend
uv run pytest -v
```

Expected: 全部PASS，无warning升级为error。

- [ ] **Step 2: 运行前端全量测试、构建和生产依赖审计**

Run:

```powershell
Set-Location frontend
npm test -- --run
npm run build
npm audit --omit=dev
```

Expected: 测试与构建成功，生产依赖无高危漏洞。

- [ ] **Step 3: 构建容器并检查健康状态**

为本地冒烟生成临时开发env，不写入Git；确认目标是工作树内`.env`后再运行：

```powershell
Set-Location ..
Copy-Item .env.example .env
$integration = -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 48 | ForEach-Object {[char]$_})
$mcpToken = -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 48 | ForEach-Object {[char]$_})
(Get-Content .env) -replace 'replace-with-at-least-32-random-characters', $integration -replace 'replace-with-separate-32-character-random-token', $mcpToken | Set-Content .env
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://127.0.0.1:8080/api/health
```

Expected: backend healthy、web up，health返回`status=ok`。冒烟完成后停止容器，但保留命名数据卷：

```powershell
docker compose down
Remove-Item -LiteralPath .env
```

- [ ] **Step 4: 检查Git差异和敏感信息**

Run:

```powershell
git diff --check
rg -n "Bearer [A-Za-z0-9_-]{32,}|ZHILIU_MCP_TOKEN=[A-Za-z0-9_-]{32,}" --glob '!*.example' --glob '!docs/superpowers/**'
git status --short
```

Expected: `git diff --check`无输出；敏感信息扫描无匹配；工作树只含计划内变更。

- [ ] **Step 5: 在核云服务器完成三层真实验收**

部署后依次确认：

```bash
cd /opt/zhiliu
docker compose ps
curl -fsS http://127.0.0.1:8080/api/health
hermes mcp test zhiliu
hermes mcp list
hermes skills list
```

微信依次发送：

```text
请检索今天最重要的三条Agent动态，整理好以后放进知流。
从今天起每天早上8点持续关注MCP和Agent工具调用的重要更新，放进知流。
给我解释一下知流是什么，不要保存任何内容。
```

Expected:

1. 第一条调用`zhiliu_publish`，知流情报或报告出现`微信Hermes`来源/`微信整理 ·`标题；
2. 第二条调用`zhiliu_create_monitor`，设置页出现启用的Cron订阅；
3. 第三条不产生新的`HermesPublication`或Subscription；
4. 重发第一条时返回同一回执且不增加情报、简报数量。

- [ ] **Step 6: 记录最终验证证据并处理必要的验证修复**

若无修复，保持工作树干净；若验证暴露计划范围内缺陷，先在对应的`backend/tests/test_mcp_*.py`或现有前端测试文件增加复现测试，再做最小修复，重新执行本Task的Step 1至Step 4。只提交该复现测试及其对应修复，提交信息使用`fix: resolve MCP integration verification defect`。

不得把服务器`.env`、真实token、完整微信消息或部署覆盖文件提交到仓库。
