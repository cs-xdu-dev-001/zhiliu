import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_rejects_default_secrets() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(
            app_env="production",
            jwt_secret="change-me",
            admin_password="demo-password",
            _env_file=None,
        )


def test_production_accepts_explicit_secrets() -> None:
    settings = Settings(
        app_env="production",
        jwt_secret="a-secure-random-secret-that-is-long-enough",
        admin_password="a-unique-admin-password",
        _env_file=None,
    )

    assert settings.app_env == "production"

