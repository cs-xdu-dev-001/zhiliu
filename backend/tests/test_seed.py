from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Briefing, IntelligenceItem, Subscription, TaskRun, User


def test_seed_creates_demo_content_once(db_session: Session) -> None:
    from app.seed import seed_database

    seed_database(db_session, demo_mode=True)
    seed_database(db_session, demo_mode=True)

    assert db_session.scalar(select(func.count()).select_from(User)) == 0
    assert db_session.scalar(select(func.count()).select_from(Subscription)) == 3
    assert db_session.scalar(select(func.count()).select_from(IntelligenceItem)) == 8
    assert db_session.scalar(select(func.count()).select_from(Briefing)) == 2
    assert db_session.scalar(select(func.count()).select_from(TaskRun)) == 4


def test_seed_without_demo_creates_nothing(db_session: Session) -> None:
    from app.seed import seed_database

    seed_database(db_session, demo_mode=False)

    assert db_session.scalar(select(func.count()).select_from(User)) == 0
    assert db_session.scalar(select(func.count()).select_from(IntelligenceItem)) == 0

