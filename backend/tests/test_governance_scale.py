from time import perf_counter

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models import Briefing, IntelligenceItem


def test_governance_lists_remain_bounded_with_realistic_volume(
    client: TestClient,
    db_session: Session,
    subscription,
) -> None:
    db_session.add_all([
        IntelligenceItem(
            subscription_id=subscription.id,
            kind="paper" if index % 3 == 0 else "news",
            title=f"规模情报{index:04d}",
            summary="用于验证治理列表在常见数据量下仍然稳定。",
            url=f"https://example.com/scale/{index}",
            source="Scale Source",
            keywords_json="[]",
            reason="规模验证",
            importance=(index % 100) / 100,
            fingerprint=f"{index:064x}",
            is_saved=index % 5 == 0,
        )
        for index in range(1000)
    ])
    db_session.add_all([
        Briefing(
            subscription_id=subscription.id,
            title=f"规模报告{index:03d}",
            kind="news",
            content="规模验证报告正文",
            item_count=10,
        )
        for index in range(100)
    ])
    db_session.commit()

    selects = 0

    def count_selects(_connection, _cursor, statement, _parameters, _context, _executemany) -> None:
        nonlocal selects
        if statement.lstrip().upper().startswith("SELECT"):
            selects += 1

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", count_selects)
    started = perf_counter()
    try:
        items = client.get("/api/items?state=saved&sort=newest&limit=20&offset=0")
        reports = client.get("/api/briefings?limit=20&offset=0")
    finally:
        elapsed = perf_counter() - started
        event.remove(engine, "before_cursor_execute", count_selects)

    assert items.status_code == 200
    assert items.json()["total"] == 200
    assert len(items.json()["items"]) == 20
    assert reports.status_code == 200
    assert reports.json()["total"] == 100
    assert len(reports.json()["items"]) == 20
    assert selects <= 5
    assert elapsed < 5
