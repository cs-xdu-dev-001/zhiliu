import json

import pytest
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
    assert receipt.subscription_id <= -1000
    assert record.enabled is True
    assert json.loads(record.keywords_json) == ["Agent", "MCP"]


def test_exact_duplicate_monitor_returns_existing(db_session: Session) -> None:
    service = MonitorService(db_session)
    first = service.create(monitor_payload())
    second = service.create(monitor_payload())

    assert second.subscription_id == first.subscription_id
    assert second.created is False
    assert db_session.scalar(select(func.count()).select_from(Subscription)) == 1


def test_disabled_duplicate_monitor_is_reenabled(db_session: Session) -> None:
    service = MonitorService(db_session)
    first = service.create(monitor_payload())
    record = db_session.get(Subscription, first.subscription_id)
    record.enabled = False
    record.keywords_json = "[]"
    db_session.commit()

    second = service.create(monitor_payload())

    db_session.refresh(record)
    assert second.subscription_id == first.subscription_id
    assert second.created is False
    assert record.enabled is True
    assert json.loads(record.keywords_json) == ["Agent", "MCP"]


def test_monitor_failure_rolls_back_and_hides_database_details(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_commit() -> None:
        raise RuntimeError("database path leaked")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    with pytest.raises(MonitorFailure, match="监测创建失败，未写入知流") as raised:
        MonitorService(db_session).create(monitor_payload())

    assert "database path leaked" not in str(raised.value)
    assert db_session.scalar(select(func.count()).select_from(Subscription)) == 0


def test_monitor_query_failure_is_wrapped_safely(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_query(*_args, **_kwargs):
        raise RuntimeError("query database detail")

    monkeypatch.setattr(db_session, "scalar", fail_query)

    with pytest.raises(MonitorFailure, match="监测创建失败，未写入知流") as raised:
        MonitorService(db_session).create(monitor_payload())

    assert "query database detail" not in str(raised.value)
