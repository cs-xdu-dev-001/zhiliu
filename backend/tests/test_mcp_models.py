import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import HermesPublication, Subscription


def test_publication_keys_are_unique(db_session: Session) -> None:
    subscription = Subscription(
        name="微信整理·情报",
        kind="news",
        keywords_json="[]",
        schedule="0 0 1 1 *",
        prompt="系统分类",
        enabled=False,
    )
    db_session.add(subscription)
    db_session.flush()
    db_session.add(
        HermesPublication(
            idempotency_key="same-key",
            payload_hash="a" * 64,
            subscription_id=subscription.id,
            item_count=0,
            skipped_count=0,
            topic="主题",
            request_summary="整理主题",
        )
    )
    db_session.commit()
    db_session.add(
        HermesPublication(
            idempotency_key="same-key",
            payload_hash="b" * 64,
            subscription_id=subscription.id,
            item_count=0,
            skipped_count=0,
            topic="另一个主题",
            request_summary="整理另一个主题",
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
