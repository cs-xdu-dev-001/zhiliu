from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import TaskRun


def test_queue_subscription_is_idempotent_while_active(
    db_session: Session,
    subscription,
) -> None:
    from app.services.scheduler import queue_subscription

    first = queue_subscription(db_session, subscription.id)
    second = queue_subscription(db_session, subscription.id)

    assert first.id == second.id
    assert db_session.scalar(select(func.count()).select_from(TaskRun)) == 1

