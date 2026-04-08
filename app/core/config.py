"""Application configuration powered by Pydantic settings."""

from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

EnvironmentName = Literal["dev", "staging", "prod"]


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = Field(default="Ebook Niche Research API", alias="APP_NAME")
    app_env: EnvironmentName = Field(default="dev", alias="APP_ENV")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    database_url: str = Field(
        default="sqlite:///./ebook_niche_research.db",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    secret_key: SecretStr = Field(default=SecretStr(""), alias="SECRET_KEY")
    export_storage_path: str = Field(default="./artifacts/exports", alias="EXPORT_STORAGE_PATH")
    export_bucket: str = Field(default="ebook-niche-research-local", alias="EXPORT_BUCKET")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        alias="CORS_ALLOWED_ORIGINS",
    )
    playwright_browsers_path: str = Field(default="0", alias="PLAYWRIGHT_BROWSERS_PATH")
    enabled_providers: Annotated[list[str], NoDecode] = Field(
        default=["google_books", "open_library"],
        alias="ENABLED_PROVIDERS",
    )
    provider_http_timeout_seconds: float = Field(default=2.0, alias="PROVIDER_HTTP_TIMEOUT_SECONDS")
    provider_http_max_retries: int = Field(default=1, alias="PROVIDER_HTTP_MAX_RETRIES")
    provider_http_retry_backoff_seconds: float = Field(default=0.25, alias="PROVIDER_HTTP_RETRY_BACKOFF_SECONDS")
    provider_user_agent: str = Field(
        default="ebook-niche-research-engine/0.1 (+local-dev)",
        alias="PROVIDER_USER_AGENT",
    )
    playwright_headless: bool = Field(default=True, alias="PLAYWRIGHT_HEADLESS")
    playwright_navigation_timeout_ms: int = Field(default=20_000, alias="PLAYWRIGHT_NAVIGATION_TIMEOUT_MS")
    playwright_action_timeout_ms: int = Field(default=10_000, alias="PLAYWRIGHT_ACTION_TIMEOUT_MS")
    marketplace_snapshot_path: str = Field(default="./artifacts/marketplace_snapshots", alias="MARKETPLACE_SNAPSHOT_PATH")
    marketplace_capture_html: bool = Field(default=True, alias="MARKETPLACE_CAPTURE_HTML")
    marketplace_capture_screenshot: bool = Field(default=False, alias="MARKETPLACE_CAPTURE_SCREENSHOT")
    marketplace_rate_limit_delay_seconds: float = Field(default=0.5, alias="MARKETPLACE_RATE_LIMIT_DELAY_SECONDS")
    marketplace_retry_backoff_seconds: float = Field(default=0.5, alias="MARKETPLACE_RETRY_BACKOFF_SECONDS")
    marketplace_max_retries: int = Field(default=1, alias="MARKETPLACE_MAX_RETRIES")

    @staticmethod
    def _parse_csv_or_json_list(value: Any) -> list[str]:
        """Support comma-separated or JSON-style list input."""
        if value is None:
            return []
        if isinstance(value, str):
            stripped_value = value.strip()
            if not stripped_value:
                return []
            if stripped_value.startswith("[") and stripped_value.endswith("]"):
                items = stripped_value[1:-1].split(",")
                return [item.strip().strip("\"'") for item in items if item.strip()]
            return [item.strip() for item in stripped_value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise TypeError("List-like settings must be provided as a string or list.")

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_allowed_origins(cls, value: Any) -> list[str]:
        """Support comma-separated or JSON-style CORS origin input."""
        return cls._parse_csv_or_json_list(value)

    @field_validator("enabled_providers", mode="before")
    @classmethod
    def parse_enabled_providers(cls, value: Any) -> list[str]:
        """Support comma-separated or JSON-style provider input."""
        return cls._parse_csv_or_json_list(value)


@lru_cache
def get_settings() -> Settings:
    """Return a cached application settings instance."""
    return Settings()
