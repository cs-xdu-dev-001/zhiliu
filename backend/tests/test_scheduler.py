from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import TaskRun
from app.models import HermesIntegration
from app.core.crypto import SecretCipher, SecretDecryptionError
from app.services.hermes import HermesClient, HermesUnavailable
from app.services.hermes_integration import HermesIntegrationService
import asyncio
from app.services import scheduler


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
    assert isinstance(client, HermesClient) and client.base_url == "https://db.example" and client.timeout_seconds == 7 and client._headers["Authorization"] == "Bearer db-key"


def test_resolver_environment_fallback(db_session, subscription):
    settings = Settings(); settings.hermes_api_key = "env-key"
    client = HermesIntegrationService(db_session, settings).resolve_client(subscription, lambda s: object())
    assert client.base_url == settings.hermes_base_url and client.timeout_seconds == 7 and client._headers["Authorization"] == "Bearer env-key"

def test_resolver_empty_database_key_falls_back(db_session, subscription):
    db_session.add(HermesIntegration(id=1, base_url="https://db.example", encrypted_api_key=None)); db_session.commit()
    client = HermesIntegrationService(db_session, Settings()).resolve_client(subscription, lambda s: object())
    assert client.base_url == Settings.hermes_base_url


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


def test_process_marks_configuration_failure(db_session, subscription, monkeypatch):
    task = TaskRun(subscription_id=subscription.id, status="queued"); db_session.add(task); db_session.commit()
    class Factory:
        def __enter__(self): return db_session
        def __exit__(self, *args): return False
    monkeypatch.setattr(scheduler, "SessionLocal", Factory)
    monkeypatch.setattr(scheduler.HermesIntegrationService, "resolve_client", lambda *a: (_ for _ in ()).throw(HermesUnavailable("尚未配置Hermes连接")))
    asyncio.run(scheduler.process_queued_tasks())
    db_session.refresh(task)
    assert task.status == "failed" and task.error_message == "尚未配置Hermes连接" and task.finished_at is not None and task.duration_ms == 0


def test_process_passes_resolved_client_to_run_service(db_session, subscription, monkeypatch):
    task = TaskRun(subscription_id=subscription.id, status="queued"); db_session.add(task); db_session.commit()
    class Factory:
        def __enter__(self): return db_session
        def __exit__(self, *args): return False
    marker = object(); seen = {}
    monkeypatch.setattr(scheduler, "SessionLocal", Factory)
    monkeypatch.setattr(scheduler.HermesIntegrationService, "resolve_client", lambda *a: marker)
    async def execute(self, task_id): seen.update(client=self.hermes_client, task_id=task_id)
    monkeypatch.setattr(scheduler.RunService, "execute_task", execute)
    asyncio.run(scheduler.process_queued_tasks())
    assert seen == {"client": marker, "task_id": task.id}


def test_process_marks_decryption_failure(db_session, subscription, monkeypatch):
    task = TaskRun(subscription_id=subscription.id, status="queued"); db_session.add(task); db_session.commit()
    class Factory:
        def __enter__(self): return db_session
        def __exit__(self, *args): return False
    monkeypatch.setattr(scheduler, "SessionLocal", Factory)
    monkeypatch.setattr(scheduler.HermesIntegrationService, "resolve_client", lambda *a: (_ for _ in ()).throw(SecretDecryptionError("密钥解密失败")))
    asyncio.run(scheduler.process_queued_tasks()); db_session.refresh(task)
    assert task.status == "failed" and task.error_message == "密钥解密失败" and task.finished_at is not None

def test_process_continues_after_first_configuration_failure(db_session, subscription, monkeypatch):
    tasks = [TaskRun(subscription_id=subscription.id, status="queued"), TaskRun(subscription_id=subscription.id, status="queued")]; db_session.add_all(tasks); db_session.commit()
    class Factory:
        def __enter__(self): return db_session
        def __exit__(self, *args): return False
    monkeypatch.setattr(scheduler, "SessionLocal", Factory); marker = object(); calls=[]; n=[0]
    def resolve(*a): n[0]+=1; return (_ for _ in ()).throw(HermesUnavailable("x")) if n[0]==1 else marker
    monkeypatch.setattr(scheduler.HermesIntegrationService, "resolve_client", resolve)
    async def execute(self, task_id): calls.append(task_id)
    monkeypatch.setattr(scheduler.RunService, "execute_task", execute)
    asyncio.run(scheduler.process_queued_tasks()); db_session.refresh(tasks[0]); db_session.refresh(tasks[1])
    assert tasks[0].status == "failed" and calls == [tasks[1].id]


def test_queue_subscription_is_idempotent_while_active(
    db_session: Session,
    subscription,
) -> None:
    from app.services.scheduler import queue_subscription

    first = queue_subscription(db_session, subscription.id)
    second = queue_subscription(db_session, subscription.id)

    assert first.id == second.id
    assert db_session.scalar(select(func.count()).select_from(TaskRun)) == 1

