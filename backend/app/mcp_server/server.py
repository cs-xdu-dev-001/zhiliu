from collections.abc import Callable
from contextlib import AbstractContextManager

from mcp.server.fastmcp import FastMCP
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.mcp_server.auth import StaticBearerAuth
from app.mcp_server.schemas import (
    IntelligenceKind,
    MonitorPayload,
    MonitorReceipt,
    PublishBriefing,
    PublishItem,
    PublishPayload,
    PublishReceipt,
)
from app.mcp_server.service import MonitorService, PublicationService


SessionFactory = Callable[[], AbstractContextManager[Session]]


def build_mcp_server(session_factory: SessionFactory = SessionLocal) -> FastMCP:
    server = FastMCP(
        "知流",
        instructions="将Hermes已完成的整理结果发布到知流，或创建用户明确要求的长期监测。",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/mcp",
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
        """发布Hermes已经完成的一次性整理结果。"""
        payload = PublishPayload.model_validate(
            {
                "idempotencyKey": idempotencyKey,
                "topic": topic,
                "kind": kind,
                "requestSummary": requestSummary,
                "items": items or [],
                "briefing": briefing,
            }
        )
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
        """仅在用户明确要求持续关注或定期整理时创建长期监测。"""
        payload = MonitorPayload(
            name=name,
            kind=kind,
            keywords=keywords,
            schedule=schedule,
            prompt=prompt,
        )
        with session_factory() as db:
            return MonitorService(db).create(payload)

    return server


def build_mcp_asgi(
    token: str,
    session_factory: SessionFactory = SessionLocal,
) -> tuple[FastMCP, StaticBearerAuth]:
    server = build_mcp_server(session_factory)
    app = StaticBearerAuth(server.streamable_http_app(), token)
    return server, app
