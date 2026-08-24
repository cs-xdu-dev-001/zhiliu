import json

import pytest

from app.models import Briefing, HermesPublication, PublicationItem, TaskRun
from app.services.hermes import HermesReport
from app.services.report_service import ReportService, validate_citations


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


def test_citation_validation_rejects_unknown_source() -> None:
    with pytest.raises(Exception, match="不存在的来源编号"):
        validate_citations("正文[2]", 1)


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
