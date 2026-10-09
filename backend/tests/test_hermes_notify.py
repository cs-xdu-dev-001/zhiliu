from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db import Base
from app.models import Subscription, TaskRun
from app.services.hermes_notify import acknowledge_notification, claim_notification, prepare_notification


def test_notification_outbox_claim_and_acknowledge() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        subscription = Subscription(
            name="AI热点", kind="news", keywords_json="[]", schedule="0 8 * * *",
            prompt="检索AI", enabled=True, notify_wechat=True,
        )
        db.add(subscription)
        db.flush()
        task = TaskRun(
            subscription_id=subscription.id, status="success", origin="subscription-hermes",
            notification_status="pending", notification_message="简报内容",
        )
        db.add(task)
        db.commit()

        settings = Settings(app_env="test", _env_file=None, weixin_push_enabled=True)
        claimed = claim_notification(db, settings)
        assert claimed and claimed["message"] == "简报内容"
        assert acknowledge_notification(db, claimed["taskId"], claimed["token"], "sent") is True
        db.refresh(task)
        assert task.notification_status == "sent"
        assert claim_notification(db, settings) is None
