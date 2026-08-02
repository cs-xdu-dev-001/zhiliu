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
        zhiliu_mcp_token="production-mcp-token-that-is-long-enough",
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


@pytest.mark.parametrize(
    "zhiliu_mcp_token",
    [
        "",
        "development-zhiliu-mcp-token-change-me",
        "replace-with-separate-32-character-random-token",
        "too-short",
    ],
)
def test_production_rejects_invalid_mcp_token(zhiliu_mcp_token: str) -> None:
    with pytest.raises(ValidationError, match="ZHILIU_MCP_TOKEN"):
        Settings(
            app_env="production",
            integration_secret_key="production-integration-secret-that-is-long-enough",
            zhiliu_mcp_token=zhiliu_mcp_token,
            _env_file=None,
        )


def test_production_rejects_reused_integration_secret() -> None:
    reused_secret = "production-shared-secret-that-is-long-enough"
    with pytest.raises(ValidationError, match="ZHILIU_MCP_TOKEN"):
        Settings(
            app_env="production",
            integration_secret_key=reused_secret,
            zhiliu_mcp_token=reused_secret,
            _env_file=None,
        )

