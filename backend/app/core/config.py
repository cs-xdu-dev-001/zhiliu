from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./data/zhiliu.db"
    scheduler_enabled: bool = True
    demo_mode: bool = True
    hermes_base_url: str = "http://127.0.0.1:8642"
    hermes_api_key: str = ""
    hermes_timeout_seconds: int = 180
    integration_secret_key: str = "development-integration-secret-key-32"
    zhiliu_mcp_token: str = "development-zhiliu-mcp-token-change-me"

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env == "production":
            placeholders = {
                "development-integration-secret-key-32",
                "replace-with-at-least-32-random-characters",
            }
            if self.integration_secret_key in placeholders or len(self.integration_secret_key) < 32:
                raise ValueError("INTEGRATION_SECRET_KEY必须替换为至少32位的随机值")
            invalid_mcp_tokens = {
                "development-zhiliu-mcp-token-change-me",
                "replace-with-separate-32-character-random-token",
            }
            if (
                self.zhiliu_mcp_token in invalid_mcp_tokens
                or len(self.zhiliu_mcp_token) < 32
                or self.zhiliu_mcp_token == self.integration_secret_key
            ):
                raise ValueError("ZHILIU_MCP_TOKEN必须替换为至少32位的独立随机值")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
