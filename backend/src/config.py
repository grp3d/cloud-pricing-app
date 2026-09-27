"""Application configuration.

Values come from environment variables (with sane local-dev defaults), never hardcoded
elsewhere, per the constitution's requirement that vendor pricing data access and the
Postgres connection be explicitly configured rather than assumed.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost/cloud_pricing_dev"

    # Base directory containing the AWS pricing Parquet tables (service_dim/, product_dim/,
    # product_attribute/, region_dim/, price_fact/), each partitioned by snapshot_date= and
    # region=. Produced by a separate upstream project; this backend only ever reads from it.
    aws_pricing_parquet_dir: str = (
        "/Users/ghubs/Development/repos/personal/cloud-pricing/DATA/pricing_aws/parquet"
    )

    # AWS region used for catalog search / pricing in v1 (single-region scope).
    aws_pricing_region: str = "us-east-1"

    # 016-canvas-icon-layout, FR-015: how often the background check looks for a newer, fully
    # written pricing snapshot (and re-runs the icon analysis when the active one changes).
    snapshot_check_interval_seconds: int = Field(default=300, ge=10)

    # 016-canvas-icon-layout, FR-018: pins the active pricing snapshot (e.g. to roll back from
    # bad upstream data). Unset = the newest snapshot marked complete in every table.
    active_snapshot_date: date | None = None

    # 016-canvas-icon-layout, US8 (FR-025): values that used to be fixed in code. Every default
    # is today's behavior; each is overridable by the upper-cased name as an environment
    # variable, and an invalid value stops startup naming the setting (FR-026). Documented in
    # docs/configuration.md.

    # Browser origins allowed to call the API (JSON list, e.g. '["http://localhost:5173"]').
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173"], min_length=1
    )

    # Catalog search page size: used when a request doesn't ask, and the most it may ask for.
    catalog_search_default_limit: int = Field(default=50, ge=1)
    catalog_search_max_limit: int = Field(default=200, ge=1)

    # PBKDF2 iterations for newly hashed passwords (existing hashes keep their own count).
    password_hash_iterations: int = Field(default=260_000, ge=100_000)

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # 017-structured-json-logging, FR-001a: one JSON object per line, or readable local-dev lines.
    log_format: Literal["json", "console"] = "json"

    @model_validator(mode="after")
    def _catalog_search_default_within_max(self) -> Settings:
        if self.catalog_search_default_limit > self.catalog_search_max_limit:
            raise ValueError(
                "catalog_search_default_limit must not exceed catalog_search_max_limit"
            )
        return self


settings = Settings()
