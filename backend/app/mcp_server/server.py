from collections.abc import Callable
from contextlib import AbstractContextManager

from mcp.server.fastmcp import FastMCP
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.mcp_server.auth import StaticBearerAuth
from app.mcp_server.schemas import (
    IntelligenceKind,
    FeedbackPriority,
    MonitorPayload,
    MonitorReceipt,
    PublishBriefing,
    PublishItem,
    PublishPayload,
    PublishReceipt,
    PreferenceListReceipt,
    PreferenceEffect,
    PreferenceKind,
    PreferencePayload,
    PreferenceReceipt,
    PreferenceRemoveReceipt,
    PreferenceScope,
    SearchPayload,
    SearchReceipt,
    SearchResult,
    DailyAttentionReceipt,
    DailyAttentionSource,
    ItemFeedbackPayload,
    ItemFeedbackReceipt,
    TaskFailurePayload,
    TaskFeedbackReceipt,
    TaskProgressPayload,
    TaskStartPayload,
)
from app.mcp_server.service import MonitorService, PublicationService, TaskFeedbackService
from app.services.preferences import PreferenceService
from app.services.search import SearchService
from app.services.item_maintenance import ItemMaintenanceService
from app.services.daily_attention import build_instruction, build_snapshot


SessionFactory = Callable[[], AbstractContextManager[Session]]


def build_mcp_server(
    session_factory: SessionFactory = SessionLocal,
    *,
    public_base_url: str = "",
) -> FastMCP:
    server = FastMCP(
        "知流",
        instructions="检索知流已有内容、读取用户偏好、维护情报，并将Hermes整理结果发布到知流。",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/mcp",
    )

    @server.tool(name="zhiliu_begin_task")
    def zhiliu_begin_task(
        traceId: str,
        topic: str,
        kind: IntelligenceKind,
        requestSummary: str,
        hermesRunId: str | None = None,
    ) -> TaskFeedbackReceipt:
        """在开始检索整理前登记任务，让知流立即显示处理状态。"""
        payload = TaskStartPayload.model_validate(
            {
                "traceId": traceId,
                "hermesRunId": hermesRunId,
                "topic": topic,
                "kind": kind,
                "requestSummary": requestSummary,
            }
        )
        with session_factory() as db:
            return TaskFeedbackService(db, public_base_url=public_base_url).begin(payload)

    @server.tool(name="zhiliu_update_task")
    def zhiliu_update_task(
        traceId: str,
        stage: str,
        hermesRunId: str | None = None,
    ) -> TaskFeedbackReceipt:
        """任务推进到理解、检索、整理或写入阶段时更新进度与心跳。"""
        payload = TaskProgressPayload.model_validate(
            {"traceId": traceId, "stage": stage, "hermesRunId": hermesRunId}
        )
        with session_factory() as db:
            return TaskFeedbackService(db, public_base_url=public_base_url).progress(payload)

    @server.tool(name="zhiliu_publish")
    def zhiliu_publish(
        idempotencyKey: str,
        traceId: str,
        topic: str,
        kind: IntelligenceKind,
        requestSummary: str,
        hermesRunId: str | None = None,
        items: list[PublishItem] | None = None,
        briefing: PublishBriefing | None = None,
    ) -> PublishReceipt:
        """发布整理结果；每条变化应给出changeType、changeBasis、sourceUrls，非首次出现还须给relatedItemId。"""
        payload = PublishPayload.model_validate(
            {
                "idempotencyKey": idempotencyKey,
                "traceId": traceId,
                "hermesRunId": hermesRunId,
                "topic": topic,
                "kind": kind,
                "requestSummary": requestSummary,
                "items": items or [],
                "briefing": briefing,
            }
        )
        with session_factory() as db:
            return PublicationService(db, public_base_url=public_base_url).publish(payload)

    @server.tool(name="zhiliu_report_failure")
    def zhiliu_report_failure(
        traceId: str,
        errorMessage: str,
        hermesRunId: str | None = None,
    ) -> TaskFeedbackReceipt:
        """本次检索、整理或写入失败时更新知流任务状态。"""
        payload = TaskFailurePayload.model_validate(
            {
                "traceId": traceId,
                "hermesRunId": hermesRunId,
                "errorMessage": errorMessage,
            }
        )
        with session_factory() as db:
            return TaskFeedbackService(db, public_base_url=public_base_url).fail(payload)

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

    @server.tool(name="zhiliu_search")
    def zhiliu_search(
        query: str,
        kind: IntelligenceKind | None = None,
        days: int | None = None,
        limit: int = 10,
    ) -> SearchReceipt:
        """搜索知流中的历史情报和报告；回答已有内容、比较和追溯问题时先调用。"""
        payload = SearchPayload(query=query, kind=kind, days=days, limit=limit)
        with session_factory() as db:
            bundle = SearchService(db).search(
                payload.query,
                kind=payload.kind,
                days=payload.days,
                limit=payload.limit,
            )
            hits = [*bundle.items, *bundle.briefings]
            return SearchReceipt(
                query=bundle.query,
                results=[
                    SearchResult(
                        result_type=hit.result_type,
                        result_id=hit.result_id,
                        kind=hit.kind,
                        title=hit.title,
                        summary=hit.summary,
                        source=hit.source,
                        source_url=hit.source_url,
                        detail_url=(
                            f"{public_base_url.rstrip('/')}/items/{hit.result_id}"
                            if public_base_url and hit.result_type == "item"
                            else f"{public_base_url.rstrip('/')}/reports/{hit.result_id}"
                            if public_base_url
                            else None
                        ),
                        created_at=hit.created_at,
                    )
                    for hit in hits
                ],
            )

    @server.tool(name="zhiliu_prepare_daily_attention")
    def zhiliu_prepare_daily_attention() -> DailyAttentionReceipt:
        """读取今日关注候选；整理后用返回的幂等键作为zhiliu_publish的idempotencyKey和traceId发布摘要。"""
        with session_factory() as db:
            snapshot = build_snapshot(db)
            return DailyAttentionReceipt(
                date=snapshot.day,
                idempotency_key=snapshot.idempotency_key,
                sources=[
                    DailyAttentionSource(
                        item_id=item.id,
                        kind=item.kind,
                        title=item.title,
                        summary=item.summary,
                        source=item.source,
                        source_url=item.url,
                        importance=item.personalized_score if item.personalized_score is not None else item.importance,
                        reasons=snapshot.reasons[item.id],
                    )
                    for item in snapshot.items
                ],
                rising_topics=[topic.name for topic in snapshot.rising_topics],
                important_change_count=snapshot.important_change_count,
                source_unavailable_count=snapshot.source_unavailable_count,
                pending_change_count=snapshot.pending_change_count,
                consecutive_failure_count=snapshot.consecutive_failure_count,
                instruction=build_instruction(snapshot),
                message="有候选内容，可整理后发布" if snapshot.items else "今日没有达到条件的重要变化，不要发布空摘要",
            )

    @server.tool(name="zhiliu_get_preferences")
    def zhiliu_get_preferences(kind: IntelligenceKind | None = None) -> PreferenceListReceipt:
        """在整理或发布前读取用户长期偏好。"""
        with session_factory() as db:
            records = PreferenceService(db).list(kind=kind)
            return PreferenceListReceipt(
                preferences=[
                    PreferenceReceipt(
                        preference_id=record.id,
                        scope=record.scope,
                        effect=record.effect,
                        value=record.value,
                        kind=record.kind,
                        note=record.note,
                        active=record.active,
                        created=False,
                    )
                    for record in records
                ]
            )

    @server.tool(name="zhiliu_save_preference")
    def zhiliu_save_preference(
        scope: PreferenceScope,
        effect: PreferenceEffect,
        value: str,
        kind: PreferenceKind = "all",
        note: str = "",
    ) -> PreferenceReceipt:
        """用户明确表达长期偏好时保存；一次性要求不要保存为长期偏好。"""
        payload = PreferencePayload(
            scope=scope,
            effect=effect,
            value=value,
            kind=kind,
            note=note,
        )
        with session_factory() as db:
            record, created = PreferenceService(db).save(
                scope=payload.scope,
                effect=payload.effect,
                value=payload.value,
                kind=payload.kind,
                note=payload.note,
            )
            return PreferenceReceipt(
                preference_id=record.id,
                scope=record.scope,
                effect=record.effect,
                value=record.value,
                kind=record.kind,
                note=record.note,
                active=record.active,
                created=created,
                message="长期偏好已保存" if created else "长期偏好已更新",
            )

    @server.tool(name="zhiliu_remove_preference")
    def zhiliu_remove_preference(preferenceId: int) -> PreferenceRemoveReceipt:
        """用户明确撤销某条长期偏好时停用该规则。"""
        with session_factory() as db:
            record = PreferenceService(db).remove(preferenceId)
            return PreferenceRemoveReceipt(
                preference_id=record.id,
                removed=not record.active,
                message="长期偏好已移除",
            )

    @server.tool(name="zhiliu_update_item")
    def zhiliu_update_item(
        itemId: int,
        title: str | None = None,
        summary: str | None = None,
        kind: IntelligenceKind | None = None,
        priority: FeedbackPriority | None = None,
        ignored: bool | None = None,
        sourceUnavailable: bool | None = None,
    ) -> ItemFeedbackReceipt:
        """仅在已知具体情报ID时根据用户反馈修订内容、优先级、忽略或原文失效状态。"""
        payload = ItemFeedbackPayload(
            itemId=itemId,
            title=title,
            summary=summary,
            kind=kind,
            priority=priority,
            ignored=ignored,
            sourceUnavailable=sourceUnavailable,
        )
        with session_factory() as db:
            record = ItemMaintenanceService(db).apply_feedback(
                payload.item_id,
                title=payload.title,
                summary=payload.summary,
                kind=payload.kind,
                priority=payload.priority,
                ignored=payload.ignored,
                source_unavailable=payload.source_unavailable,
            )
            return ItemFeedbackReceipt(
                item_id=record.id,
                title=record.title,
                importance=record.importance,
                ignored=record.is_ignored,
                source_unavailable=record.source_unavailable,
                message="情报已按反馈更新，修改记录已保留",
                detail_url=(
                    f"{public_base_url.rstrip('/')}/items/{record.id}" if public_base_url else None
                ),
            )

    return server


def build_mcp_asgi(
    token: str,
    session_factory: SessionFactory = SessionLocal,
    *,
    public_base_url: str = "",
) -> tuple[FastMCP, StaticBearerAuth]:
    server = build_mcp_server(session_factory, public_base_url=public_base_url)
    app = StaticBearerAuth(server.streamable_http_app(), token)
    return server, app
