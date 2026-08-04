import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Briefing,
    HermesPublication,
    HermesQualityDecision,
    IntelligenceItem,
    PublicationItem,
    Subscription,
    TaskRun,
)
from app.services.run_service import item_fingerprint


def seed_database(
    db: Session,
    *,
    demo_mode: bool,
) -> None:
    if not demo_mode or db.scalar(select(Subscription).limit(1)) is not None:
        return

    subscriptions = [
        Subscription(
            name="AI每日热点",
            kind="news",
            keywords_json='["AI Agent", "RAG", "代码智能体"]',
            schedule="0 8 * * *",
            prompt="检索过去24小时AI Agent、RAG和代码智能体领域的重要新闻，只保留五条。",
        ),
        Subscription(
            name="Agent论文周报",
            kind="paper",
            keywords_json='["LLM Agent", "Tool Use", "RAG"]',
            schedule="0 9 * * 1",
            prompt="检索过去7天LLM Agent、工具调用和RAG相关论文，筛选最值得阅读的五篇。",
        ),
        Subscription(
            name="AI工程岗位",
            kind="job",
            keywords_json='["AI应用开发", "Agent工程", "Python"]',
            schedule="0 18 * * 5",
            prompt="检索近期适合应届生的AI应用开发与Agent工程岗位。",
        ),
    ]
    db.add_all(subscriptions)
    db.flush()

    now = datetime.now(timezone.utc)
    items_data = [
        (0, "news", "Hermes Agent增加异步Run接口", "外部系统现在可以创建、跟踪和停止长时间Agent任务。", "https://example.com/hermes-runs", "Hermes", 0.96),
        (0, "news", "开源RAG评测工具发布新版本", "新版本补充检索归因和引用覆盖率指标。", "https://example.com/rag-eval", "Open Source Weekly", 0.84),
        (0, "news", "代码Agent开始强调仓库级上下文", "新工作流将代码图谱和执行轨迹结合。", "https://example.com/code-agent-context", "AI Engineering", 0.81),
        (1, "paper", "Reliable Tool Use for Language Model Agents", "论文系统分析Agent工具调用失败的发生与恢复。", "https://arxiv.org/abs/2607.00001", "arXiv", 0.94),
        (1, "paper", "Long-Horizon Memory for Research Agents", "研究长任务中记忆压缩与证据保留。", "https://arxiv.org/abs/2607.00002", "arXiv", 0.89),
        (1, "paper", "Evaluating Retrieval in Agentic RAG", "提出面向多步Agentic RAG的检索评测方法。", "https://arxiv.org/abs/2607.00003", "arXiv", 0.86),
        (2, "job", "AI Agent应用开发工程师", "负责Agent工具调用、RAG和业务流程落地。", "https://jobs.example.com/agent-engineer", "Example Jobs", 0.78),
        (2, "job", "LLM平台后端开发", "负责模型网关、调用追踪和应用服务。", "https://jobs.example.com/llm-backend", "Example Jobs", 0.74),
    ]
    items = []
    for index, (sub_index, kind, title, summary, url, source, importance) in enumerate(items_data):
        item = IntelligenceItem(
                subscription_id=subscriptions[sub_index].id,
                kind=kind,
                title=title,
                summary=summary,
                url=url,
                source=source,
                published_at=now - timedelta(hours=index * 5),
                keywords_json=json.dumps([kind, "AI"], ensure_ascii=False),
                reason="与当前关注主题高度相关",
                importance=importance,
                fingerprint=item_fingerprint(title, url),
            )
        db.add(item)
        items.append(item)
    db.flush()

    briefings = [
        Briefing(
                subscription_id=subscriptions[0].id,
                title="AI热点日报",
                kind="news",
                content="今日的共同主线是Agent从对话转向可追踪、可恢复的长任务执行。",
                item_count=3,
                period_start=now - timedelta(days=1),
                period_end=now,
            ),
        Briefing(
                subscription_id=subscriptions[1].id,
                title="Agent论文周报",
                kind="paper",
                content="本周论文集中关注工具调用可靠性、长程记忆与Agentic RAG评测。",
                item_count=3,
                period_start=now - timedelta(days=7),
                period_end=now,
            ),
    ]
    db.add_all(briefings)
    db.flush()
    tasks = [
            TaskRun(subscription_id=subscriptions[0].id, hermes_run_id="demo-hermes-news", origin="subscription-hermes", topic="AI每日热点", request_summary="演示：检索并整理过去24小时重要AI动态", status="success", stage="completed", result_summary="新增3条情报，复用0条，生成报告《AI热点日报》", finished_at=now, duration_ms=8420),
            TaskRun(subscription_id=subscriptions[1].id, hermes_run_id="demo-hermes-paper", origin="subscription-hermes", topic="Agent论文周报", request_summary="演示：检索并整理过去7天值得阅读的Agent论文", status="success", stage="completed", result_summary="新增3条情报，复用0条，生成报告《Agent论文周报》", finished_at=now, duration_ms=12130),
            TaskRun(subscription_id=subscriptions[2].id, origin="subscription-hermes", topic="AI工程岗位", request_summary="检索近期适合应届生的AI工程岗位", status="failed", stage="failed", finished_at=now, duration_ms=3100, error_message="演示：来源暂时不可用"),
            TaskRun(subscription_id=subscriptions[0].id, origin="subscription-hermes", topic="AI每日热点", request_summary="检索过去24小时重要AI动态", status="success", stage="completed", result_summary="任务已完成", finished_at=now, duration_ms=7790),
    ]
    db.add_all(tasks)
    db.flush()

    publications = [
        HermesPublication(
            idempotency_key="demo-publication-news",
            payload_hash="1" * 64,
            subscription_id=subscriptions[0].id,
            briefing_id=briefings[0].id,
            trace_id="demo-trace-news",
            hermes_run_id=tasks[0].hermes_run_id,
            task_run_id=tasks[0].id,
            item_count=3,
            skipped_count=0,
            topic="AI每日热点",
            request_summary="演示：检索并整理过去24小时重要AI动态",
            origin="subscription-hermes",
        ),
        HermesPublication(
            idempotency_key="demo-publication-paper",
            payload_hash="2" * 64,
            subscription_id=subscriptions[1].id,
            briefing_id=briefings[1].id,
            trace_id="demo-trace-paper",
            hermes_run_id=tasks[1].hermes_run_id,
            task_run_id=tasks[1].id,
            item_count=3,
            skipped_count=0,
            topic="Agent论文周报",
            request_summary="演示：检索并整理过去7天值得阅读的Agent论文",
            origin="subscription-hermes",
        ),
    ]
    db.add_all(publications)
    db.flush()
    db.add_all(
        PublicationItem(
            publication_id=publication.id,
            item_id=item.id,
            ordinal=ordinal,
            was_inserted=True,
        )
        for publication, source_items in (
            (publications[0], items[:3]),
            (publications[1], items[3:6]),
        )
        for ordinal, item in enumerate(source_items)
    )
    db.add_all(
        HermesQualityDecision(
            publication_id=publication.id,
            item_id=item.id,
            action="inserted",
            reason_code="accepted",
            reason="演示内容通过质量检查并写入",
            kind=item.kind,
            title=item.title,
            summary=item.summary,
            url=item.url,
            source=item.source,
            keywords_json=item.keywords_json,
            importance=item.importance,
        )
        for publication, source_items in ((publications[0], items[:3]), (publications[1], items[3:6]))
        for item in source_items
    )
    db.commit()

