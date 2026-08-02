from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import TaskRun
from app.models import HermesIntegration
from app.core.crypto import SecretCipher, SecretDecryptionError
from app.services.hermes import HermesClient, HermesUnavailable
from app.services.hermes_integration import HermesIntegrationService


class Settings:
    integration_secret_key = "integration-secret-at-least-32-characters"
    hermes_timeout_seconds = 7
    hermes_base_url = "https://env.example"
    hermes_api_key = "env-key"
    demo_mode = False


def test_resolver_prefers_database(db_session, subscription):
    cipher = SecretCipher(Settings.integration_secret_key)
    db_session.add(HermesIntegration(id=1, base_url="https://db.example", encrypted_api_key=cipher.encrypt("db-key")))
    db_session.commit()
    client = HermesIntegrationService(db_session, Settings()).resolve_client(subscription, lambda s: object())
    assert isinstance(client, HermesClient) and client.base_url == "https://db.example" and client._headers["Authorization"] == "Bearer db-key"


def test_resolver_environment_fallback(db_session, subscription):
    settings = Settings(); settings.hermes_api_key = "env-key"
    client = HermesIntegrationService(db_session, settings).resolve_client(subscription, lambda s: object())
    assert client.base_url == settings.hermes_base_url and client._headers["Authorization"] == "Bearer env-key"


def test_resolver_demo_and_unavailable(db_session, subscription):
    settings = Settings(); settings.hermes_api_key = ""; settings.demo_mode = True
    marker = object()
    assert HermesIntegrationService(db_session, settings).resolve_client(subscription, lambda s: marker) is marker
    settings.demo_mode = False
    try:
        HermesIntegrationService(db_session, settings).resolve_client(subscription, lambda s: marker)
    except HermesUnavailable as exc:
        assert str(exc) == "尚未配置Hermes连接"
    else:
        raise AssertionError("expected HermesUnavailable")


def test_resolver_corrupt_database_key_does_not_fallback(db_session, subscription):
    db_session.add(HermesIntegration(id=1, base_url="https://db.example", encrypted_api_key="corrupt")); db_session.commit()
    try:
        HermesIntegrationService(db_session, Settings()).resolve_client(subscription, lambda s: object())
    except SecretDecryptionError:
        pass
    else:
        raise AssertionError("expected SecretDecryptionError")


def test_queue_subscription_is_idempotent_while_active(
    db_session: Session,
    subscription,
) -> None:
    from app.services.scheduler import queue_subscription

    first = queue_subscription(db_session, subscription.id)
    second = queue_subscription(db_session, subscription.id)

    assert first.id == second.id
    assert db_session.scalar(select(func.count()).select_from(TaskRun)) == 1

