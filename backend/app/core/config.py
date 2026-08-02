from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./data/zhiliu.db"
    jwt_secret: str = "development-only-secret-change-me-32"
    cookie_secure: bool = False
    scheduler_enabled: bool = True
    demo_mode: bool = True
    admin_username: str = "admin"
    admin_password: str = "demo-password"
    hermes_base_url: str = "http://127.0.0.1:8642"
    hermes_api_key: str = ""
    hermes_timeout_seconds: int = 180

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env == "production":
            if self.jwt_secret in {"change-me", "development-only-secret-change-me-32"} or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET必须替换为至少32位的随机值")
            if self.admin_password == "demo-password" or len(self.admin_password) < 12:
                raise ValueError("ADMIN_PASSWORD必须替换为至少12位的独立密码")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
