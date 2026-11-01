
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # Application
    app_name: str = "slabsense"
    environment: str = "local"

    # Gemini provider
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        le=120,
    )

    # Fallback and retry
    gemini_fallback_model: str | None = None
    gemini_max_retries: int = Field(
        default=1,
        ge=0,
        le=3,
    )
    gemini_retry_initial_delay_seconds: float = Field(
        default=1.0,
        gt=0,
        le=30,
    )
    gemini_retry_max_delay_seconds: float = Field(
        default=4.0,
        gt=0,
        le=60,
    )

    # Database configuration
    usage_database_url: str | None = None
    usage_database_path: str = "data/slabsense_usage.sqlite3"

    # PostgreSQL connection for host-side migration.
    # Docker Compose uses db:5432 internally.
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5433, ge=1, le=65535)
    postgres_db: str = "slabsense"
    postgres_user: str = "slabsense_app"
    postgres_password: SecretStr | None = None

    # Pricing assumption
    usage_pricing_tier: Literal[
        "standard_paid",
        "free_tier",
    ] = "standard_paid"

    # Gemini 3.5 Flash-Lite pricing per million tokens (USD)
    gemini_35_flash_lite_input_usd_per_million: Decimal = Field(
        default=Decimal("0.30"),
        ge=0,
    )
    gemini_35_flash_lite_output_usd_per_million: Decimal = Field(
        default=Decimal("2.50"),
        ge=0,
    )
    gemini_35_flash_lite_cached_input_usd_per_million: Decimal = Field(
        default=Decimal("0.03"),
        ge=0,
    )

    # Gemini 3.6 Flash pricing per million tokens (USD)
    # Standard paid-tier rates through December 31, 2026.
    gemini_36_flash_input_usd_per_million: Decimal = Field(
        default=Decimal("0.75"),
        ge=0,
    )
    gemini_36_flash_output_usd_per_million: Decimal = Field(
        default=Decimal("3.75"),
        ge=0,
    )
    gemini_36_flash_cached_input_usd_per_million: Decimal = Field(
        default=Decimal("0.075"),
        ge=0,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
