import json

import pytest

from app.models import Briefing, HermesPublication, PublicationItem, TaskRun
from app.services.hermes import HermesReport
from app.services.report_service import (
    ReportService,
    build_version_diff,
    source_evidence_status,
    validate_citations,
)


class FakeReportClient:
    async def execute_report(self, prompt: str) -> HermesReport:
        assert "不可信数据" in prompt
        return HermesReport(
            run_id="hermes-report-1",
            title="Agent趋势报告",
            kind="news",
            content="工具调用可靠性正在提高[1]。",
            raw_output='{"title":"Agent趋势报告"}',
        )


class InvalidCitationReportClient:
    async def execute_report(self, prompt: str) -> HermesReport:
        return HermesReport(
            run_id="hermes-report-invalid",
            title="错误引用报告",
            kind="news",
            content="引用不存在来源[99]。",
            raw_output='{"title":"错误引用报告"}',
        )


def test_citation_validation_rejects_unknown_source() -> None:
    with pytest.raises(Exception, match="不存在的来源编号"):
        validate_citations("正文[2]", 1)


def test_source_evidence_never_claims_fact_verification() -> None:
    assert source_evidence_status(
        citation_number=1,
        cited_numbers={1},
        url="https://example.com/source",
        is_invalid=False,
        source_unavailable=False,
    )[0] == "traceable"
    assert source_evidence_status(
        citation_number=1,
        cited_numbers={1},
        url="javascript:alert(1)",
        is_invalid=False,
        source_unavailable=False,
    )[0] == "unsafe-link"
    assert source_evidence_status(
        citation_number=1,
        cited_numbers=set(),
        url="https://example.com/source",
        is_invalid=False,
        source_unavailable=False,
    )[0] == "unreferenced"


def test_version_diff_bounds_long_report_work() -> None:
    previous = Briefing(id=1, subscription_id=1, title="旧版", kind="news", content="\n".join(f"旧段落{i}" for i in range(2000)), item_count=1, version_number=1)
    current = Briefing(id=2, subscription_id=1, title="新版", kind="news", content="\n".join(f"新段落{i}" for i in range(2000)), item_count=1, version_number=2)

    result = build_version_diff(previous, current, [1], [1, 2])

    assert result["condensed"] is True
    assert len(result["changes"]) == 8
    assert result["added_source_ids"] == [2]
    assert result["removed_source_ids"] == []


@pytest.mark.asyncio
async def test_report_service_persists_report_sources_and_trace(db_session, seeded_item) -> None:
    task = TaskRun(
        subscription_id=seeded_item.subscription_id,
        trace_id="report-trace-1",
        origin="web-report",
        request_summary="突出影响",
        report_item_ids_json=json.dumps([seeded_item.id]),
        report_series_id="series-report-1",
        report_version_number=1,
    )
    db_session.add(task)
    db_session.commit()

    await ReportService(db_session, FakeReportClient()).execute_task(task.id)

    db_session.refresh(task)
    briefing = db_session.query(Briefing).filter_by(generation_task_id=task.id).one()
    publication = db_session.query(HermesPublication).filter_by(task_run_id=task.id).one()
    link = db_session.query(PublicationItem).filter_by(publication_id=publication.id).one()
    assert task.status == "success"
    assert briefing.citation_status == "valid"
    assert briefing.version_number == 1
    assert link.item_id == seeded_item.id
    assert publication.trace_id == "report-trace-1"
    assert publication.item_count == 1
    assert publication.skipped_count == 0


@pytest.mark.asyncio
async def test_invalid_report_does_not_pollute_current_versions(db_session, seeded_item) -> None:
    current = Briefing(
        subscription_id=seeded_item.subscription_id,
        title="当前有效版本",
        kind="news",
        content="有效正文[1]",
        item_count=1,
        series_id="series-safe-failure",
        version_number=1,
    )
    task = TaskRun(
        subscription_id=seeded_item.subscription_id,
        trace_id="report-invalid-citation",
        origin="web-report",
        request_summary="生成新版",
        report_item_ids_json=json.dumps([seeded_item.id]),
        report_series_id="series-safe-failure",
        report_version_number=2,
    )
    db_session.add_all([current, task])
    db_session.commit()

    await ReportService(db_session, InvalidCitationReportClient()).execute_task(task.id)

    db_session.refresh(task)
    assert task.status == "failed"
    assert "不存在的来源编号" in task.error_message
    assert db_session.query(Briefing).filter_by(series_id="series-safe-failure").count() == 1
    assert db_session.query(HermesPublication).filter_by(task_run_id=task.id).count() == 0
