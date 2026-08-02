from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.crypto import SecretCipher, SecretDecryptionError
from app.models import HermesIntegration
from app.schemas import HermesConnectionResponse, HermesConnectionUpdate
from app.services.hermes import HermesClient, HermesError, HermesUnauthorized, HermesUnavailable

class HermesIntegrationService:
    def __init__(self, db: Session, settings) -> None:
        self.db, self.settings = db, settings
        self.cipher = SecretCipher(settings.integration_secret_key)

    def get_record(self):
        return self.db.scalar(select(HermesIntegration).where(HermesIntegration.id == 1))

    def resolve_client(self, subscription, demo_client_factory):
        """Resolve the Hermes client for a task using managed, then environment config."""
        record = self.get_record()
        if record is not None and record.encrypted_api_key:
            # Deliberately let SecretDecryptionError propagate for corrupt managed config.
            key = self.cipher.decrypt(record.encrypted_api_key)
            return HermesClient(
                base_url=record.base_url,
                api_key=key,
                timeout_seconds=self.settings.hermes_timeout_seconds,
            )
        if self.settings.hermes_api_key:
            return HermesClient(
                base_url=self.settings.hermes_base_url,
                api_key=self.settings.hermes_api_key,
                timeout_seconds=self.settings.hermes_timeout_seconds,
            )
        if self.settings.demo_mode:
            return demo_client_factory(subscription)
        raise HermesUnavailable("尚未配置Hermes连接")

    def response(self, record=None) -> HermesConnectionResponse:
        record = record or self.get_record()
        if record is None:
            return HermesConnectionResponse(message="尚未配置Hermes连接")
        return HermesConnectionResponse(base_url=record.base_url, api_key_configured=bool(record.encrypted_api_key), api_key_hint=record.api_key_hint, status=record.last_status, message=record.last_message, checked_at=record.last_checked_at, version=record.hermes_version)

    @staticmethod
    def _validate_url(value: str) -> None:
        parsed = urlparse(value)
        try:
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("baseUrl端口无效") from exc
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("baseUrl必须是包含主机名的http或https地址")

    async def save_and_test(self, payload: HermesConnectionUpdate) -> HermesConnectionResponse:
        base_url = payload.base_url.strip().rstrip("/")
        self._validate_url(base_url)
        api_key = payload.api_key.strip()
        record = self.get_record()
        is_new = record is None
        if record is None:
            record = HermesIntegration(id=1, base_url=base_url)
            self.db.add(record)
        else:
            record.base_url = base_url
        if api_key:
            record.encrypted_api_key = self.cipher.encrypt(api_key)
            record.api_key_hint = "••••" + api_key[-4:] if len(api_key) > 4 else "••••"
        try:
            self.db.commit(); self.db.refresh(record)
        except IntegrityError as integrity_exc:
            if not is_new:
                self.db.rollback(); raise
            self.db.rollback()
            record = self.get_record()
            if record is None:
                raise integrity_exc
            record.base_url = base_url
            if api_key:
                record.encrypted_api_key = self.cipher.encrypt(api_key)
                record.api_key_hint = "••••" + api_key[-4:] if len(api_key) > 4 else "••••"
            try:
                self.db.commit(); self.db.refresh(record)
            except Exception:
                self.db.rollback(); raise
        except Exception:
            self.db.rollback(); raise
        return await self.test(record)

    async def test(self, record=None) -> HermesConnectionResponse:
        record = record or self.get_record()
        if record is None or not record.base_url or not record.encrypted_api_key:
            if record is not None:
                record.last_status, record.last_message, record.last_checked_at = "unconfigured", "尚未配置Hermes连接", datetime.now(timezone.utc)
                record.hermes_version = None
                try:
                    self.db.commit()
                except Exception:
                    self.db.rollback(); raise
            return self.response(record)
        checked = datetime.now(timezone.utc)
        record.hermes_version = None
        try:
            key = self.cipher.decrypt(record.encrypted_api_key)
            probe = await HermesClient(base_url=record.base_url, api_key=key, timeout_seconds=self.settings.hermes_timeout_seconds).probe()
            record.last_status, record.last_message, record.hermes_version = "connected", "Hermes连接正常", probe.version
        except HermesUnauthorized as exc:
            record.last_status, record.last_message, record.hermes_version = "unauthorized", str(exc), None
        except HermesUnavailable as exc:
            record.last_status, record.last_message, record.hermes_version = "unreachable", str(exc), None
        except SecretDecryptionError as exc:
            record.last_status, record.last_message, record.hermes_version = "error", str(exc), None
        except HermesError:
            record.last_status, record.last_message, record.hermes_version = "error", "Hermes连接测试失败", None
        except Exception:
            record.last_status, record.last_message, record.hermes_version = "error", "Hermes连接测试失败", None
        record.last_checked_at = checked
        try:
            self.db.commit(); self.db.refresh(record)
        except Exception:
            self.db.rollback(); raise
        return self.response(record)
