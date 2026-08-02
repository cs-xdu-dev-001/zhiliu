import pytest
from datetime import datetime
from app.services import hermes_integration as integration_service
from app.services.hermes import HermesProbe, HermesUnauthorized, HermesUnavailable, HermesError

from app.core.crypto import SecretCipher
from app.core.crypto import SecretDecryptionError
from app.models import HermesIntegration
from app.schemas import HermesConnectionUpdate

def test_get_unconfigured_does_not_create_record(auth_client, db_session):
    response = auth_client.get("/api/integrations/hermes")
    assert response.status_code == 200
    assert response.json()["status"] == "unconfigured"
    assert response.json()["apiKeyConfigured"] is False
    assert "apiKeyConfigured" in response.text and "apiKeyHint" in response.text
    assert db_session.query(HermesIntegration).count() == 0

def test_put_saves_and_probes(auth_client, db_session, monkeypatch):
    calls = []
    async def probe(self):
        calls.append(1)
        return HermesProbe(version="1.2.3")
    monkeypatch.setattr(integration_service.HermesClient, "probe", probe)
    secret = "secret-a9f2"
    response = auth_client.put("/api/integrations/hermes", json={"baseUrl":"https://hermes.example.com", "apiKey":secret})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "connected" and body["version"] == "1.2.3"
    assert body["apiKeyHint"] == "••••a9f2" and len(calls) == 1
    assert secret not in response.text
    record = db_session.query(HermesIntegration).one()
    assert record.encrypted_api_key != secret
    assert integration_service.HermesIntegrationService(db_session, __import__('app.core.config', fromlist=['get_settings']).get_settings()).cipher.decrypt(record.encrypted_api_key) == secret

def test_empty_key_keeps_old(auth_client, db_session, monkeypatch):
    async def probe(self): return HermesProbe(version="1")
    monkeypatch.setattr(integration_service.HermesClient, "probe", probe)
    auth_client.put("/api/integrations/hermes", json={"baseUrl":"https://hermes.example.com", "apiKey":"old-key"})
    first = db_session.query(HermesIntegration).one().encrypted_api_key
    response = auth_client.put("/api/integrations/hermes", json={"baseUrl":"https://hermes.example.com", "apiKey":""})
    assert response.status_code == 200
    record = db_session.query(HermesIntegration).one()
    assert record.encrypted_api_key == first and response.json()["apiKeyHint"] == "••••-key"

def test_short_key_is_masked_and_inputs_stripped(auth_client, db_session, monkeypatch):
    async def probe(self): return HermesProbe(version="1")
    monkeypatch.setattr(integration_service.HermesClient, "probe", probe)
    response = auth_client.put("/api/integrations/hermes", json={"baseUrl":" https://hermes.example.com/ ", "apiKey":" ab "})
    assert response.json()["baseUrl"] == "https://hermes.example.com"
    assert response.json()["apiKeyHint"] == "••••" and " ab " not in response.text

def test_generic_error_safe_and_clears_version(auth_client, monkeypatch):
    async def good(self): return HermesProbe(version="9")
    monkeypatch.setattr(integration_service.HermesClient, "probe", good)
    auth_client.put("/api/integrations/hermes", json={"baseUrl":"https://hermes.example.com", "apiKey":"secret"})
    async def bad(self): raise HermesError("secret-leak")
    monkeypatch.setattr(integration_service.HermesClient, "probe", bad)
    response = auth_client.post("/api/integrations/hermes/test")
    assert response.json()["status"] == "error" and response.json()["message"] == "Hermes连接测试失败"
    assert "secret-leak" not in response.text and response.json()["version"] is None

@pytest.mark.parametrize("url", ["ftp://hermes.example.com", "https:///missing-host"])
def test_invalid_url(auth_client, url):
    response = auth_client.put("/api/integrations/hermes", json={"baseUrl":url, "apiKey":"x"})
    assert response.status_code == 422

@pytest.mark.parametrize("exc,status", [(HermesUnauthorized("no"), "unauthorized"), (HermesUnavailable("down"), "unreachable"), (HermesError("bad"), "error")])
def test_test_status_mapping(auth_client, db_session, monkeypatch, exc, status):
    async def probe(self): raise exc
    monkeypatch.setattr(integration_service.HermesClient, "probe", probe)
    auth_client.put("/api/integrations/hermes", json={"baseUrl":"https://hermes.example.com", "apiKey":"key"})
    response = auth_client.post("/api/integrations/hermes/test")
    assert response.json()["status"] == status
    assert db_session.query(HermesIntegration).one().last_checked_at is not None

def test_test_unconfigured_skips_probe(auth_client, monkeypatch):
    def fail(*args, **kwargs): raise AssertionError("probe called")
    monkeypatch.setattr(integration_service.HermesClient, "probe", fail)
    response = auth_client.post("/api/integrations/hermes/test")
    assert response.json()["status"] == "unconfigured"

def test_singleton_race_replays_update(monkeypatch):
    class FakeDB:
        def __init__(self): self.row = None; self.calls = 0
        def scalar(self, _): return self.row
        def add(self, row): self.pending = row
        def commit(self):
            self.calls += 1
            if self.calls == 1:
                self.rollback()
                self.row = HermesIntegration(id=1, base_url="https:// 경쟁", encrypted_api_key=SecretCipher("integration-secret-at-least-32-characters").encrypt("old"), api_key_hint="••••old")
                raise __import__('sqlalchemy').exc.IntegrityError("x", {}, Exception())
            if self.row is None: self.row = getattr(self, 'pending', self.row)
        def refresh(self, row): pass
        def rollback(self): pass
    class Settings: integration_secret_key="integration-secret-at-least-32-characters"; hermes_timeout_seconds=1
    db = FakeDB()
    async def probe(self): return HermesProbe(version="r")
    monkeypatch.setattr(integration_service.HermesClient, "probe", probe)
    result = __import__('asyncio').run(integration_service.HermesIntegrationService(db, Settings()).save_and_test(HermesConnectionUpdate(base_url="https://winner", api_key="")))
    assert db.row.base_url == "https://winner" and SecretCipher(Settings.integration_secret_key).decrypt(db.row.encrypted_api_key) == "old"
    assert result.status == "connected"

def test_unconfigured_record_commit_failure_rolls_back():
    class DB:
        def __init__(self): self.row = HermesIntegration(id=1, base_url="https://h", encrypted_api_key=None); self.rolled = False
        def scalar(self, _): return self.row
        def commit(self): raise RuntimeError("db")
        def rollback(self): self.rolled = True
    class Settings: integration_secret_key="integration-secret-at-least-32-characters"; hermes_timeout_seconds=1
    db = DB()
    with pytest.raises(RuntimeError):
        __import__('asyncio').run(integration_service.HermesIntegrationService(db, Settings()).test())
    assert db.rolled


def test_secret_cipher_round_trip():
    cipher = SecretCipher("integration-secret-at-least-32-characters")
    encrypted = cipher.encrypt("hermes-api-key")
    assert encrypted != "hermes-api-key"
    assert cipher.decrypt(encrypted) == "hermes-api-key"


def test_secret_cipher_rejects_short_key():
    with pytest.raises(ValueError):
        SecretCipher("too-short")


def test_secret_cipher_rejects_wrong_key_and_tampering():
    cipher = SecretCipher("integration-secret-at-least-32-characters")
    encrypted = cipher.encrypt("hermes-api-key")
    expected = "Hermes密钥无法解密，请重新配置"
    with pytest.raises(SecretDecryptionError, match=expected):
        SecretCipher("another-integration-secret-at-least-32").decrypt(encrypted)
    with pytest.raises(SecretDecryptionError, match=expected):
        cipher.decrypt(encrypted[:-1] + ("A" if encrypted[-1] != "A" else "B"))


def test_hermes_integration_defaults(db_session):
    integration = HermesIntegration(base_url="http://127.0.0.1:8642")
    db_session.add(integration)
    db_session.commit()
    db_session.refresh(integration)
    assert integration.id == 1
    assert integration.base_url == "http://127.0.0.1:8642"
    assert integration.last_status == "unconfigured"
    assert integration.last_message == "尚未配置Hermes连接"
    assert integration.encrypted_api_key is None
    assert integration.api_key_hint is None
    assert integration.hermes_version is None
    assert integration.last_checked_at is None
    assert integration.created_at is not None
    assert integration.updated_at is not None
