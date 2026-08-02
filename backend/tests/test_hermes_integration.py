from app.core.crypto import SecretCipher
from app.models import HermesIntegration


def test_secret_cipher_round_trip():
    cipher = SecretCipher("integration-secret-at-least-32-characters")
    encrypted = cipher.encrypt("hermes-api-key")
    assert encrypted != "hermes-api-key"
    assert cipher.decrypt(encrypted) == "hermes-api-key"


def test_hermes_integration_defaults(db_session):
    integration = HermesIntegration(base_url="http://127.0.0.1:8642")
    db_session.add(integration)
    db_session.commit()
    db_session.refresh(integration)
    assert integration.last_status == "unconfigured"
    assert integration.last_message == "尚未配置Hermes连接"
    assert integration.encrypted_api_key is None
