import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_rejects_default_secrets() -> None:
    with pytest.raises(ValidationError, match="INTEGRATION_SECRET_KEY"):
        Settings(
            app_env="production",
            _env_file=None,
        )


def test_production_accepts_explicit_secrets() -> None:
    settings = Settings(
        app_env="production",
        integration_secret_key="production-integration-secret-that-is-long-enough",
        _env_file=None,
    )

    assert settings.app_env == "production"


@pytest.mark.parametrize(
    "integration_secret_key",
    [
        "development-integration-secret-key-32",
        "replace-with-at-least-32-random-characters",
        "too-short",
    ],
)
def test_production_rejects_invalid_integration_secret(integration_secret_key: str) -> None:
    with pytest.raises(ValidationError, match="INTEGRATION_SECRET_KEY"):
        Settings(
            app_env="production",
            integration_secret_key=integration_secret_key,
            _env_file=None,
        )

