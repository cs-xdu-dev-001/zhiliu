from contextlib import nullcontext

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import main as main_module
from app.core.config import Settings
from app.db import get_db
from app.main import create_app
from app.models import IntelligenceItem, Subscription


@pytest.mark.asyncio
async def test_official_client_discovers_and_calls_zhiliu_tools(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "test-mcp-token-that-is-at-least-32-characters"
    settings = Settings(
        scheduler_enabled=False,
        zhiliu_mcp_token=token,
        _env_file=None,
    )
    monkeypatch.setattr(main_module, "SessionLocal", lambda: nullcontext(db_session))
    app = create_app(
        start_background_scheduler=False,
        settings=settings,
        mcp_session_factory=lambda: nullcontext(db_session),
    )

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {token}"}

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost:8000",
            headers=headers,
        ) as http_client:
            async with streamable_http_client(
                "http://localhost:8000/api/mcp",
                http_client=http_client,
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert {tool.name for tool in tools.tools} == {
                        "zhiliu_begin_task",
                        "zhiliu_publish",
                        "zhiliu_report_failure",
                        "zhiliu_create_monitor",
                    }
                    result = await session.call_tool(
                        "zhiliu_publish",
                        arguments={
                            "idempotencyKey": "official-client-test",
                            "traceId": "trace-official-client-test",
                            "topic": "MCP测试",
                            "kind": "news",
                            "requestSummary": "保存MCP测试结果",
                            "items": [
                                {
                                    "title": "MCP联通",
                                    "summary": "官方客户端调用成功。",
                                    "url": "https://example.com/mcp",
                                    "source": "Example",
                                    "keywords": ["MCP"],
                                    "reason": "验证链路",
                                    "importance": 0.8,
                                }
                            ],
                        },
                    )
                    assert result.isError is False

            items_response = await http_client.get("/api/items")

    assert items_response.status_code == 200
    published_item = next(
        item for item in items_response.json()["items"] if item["title"] == "MCP联通"
    )
    assert published_item["source"] == "Example · 微信Hermes"

    assert (
        db_session.scalar(
            select(IntelligenceItem).where(IntelligenceItem.title == "MCP联通")
        )
        is not None
    )
    category = db_session.scalar(
        select(Subscription).where(Subscription.name == "微信整理·情报")
    )
    assert category is not None
