"""Application configuration.

Values come from environment variables (with sane local-dev defaults), never hardcoded
elsewhere, per the constitution's requirement that vendor pricing data access and the
Postgres connection be explicitly configured rather than assumed.
"""

from __future__ import annotations

import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Literal, NamedTuple
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_OLD_DATA_SETTING_MESSAGE = (
    "AWS_PRICING_PARQUET_DIR was replaced by PRICING_DATA_URI (the pipeline storage root, "
    "e.g. file:///…/DATA/pipeline). See docs/configuration.md."
)
_DUCKDB_SIZE = re.compile(r"^\d+(\.\d+)?\s*(B|KB|MB|GB|TB|KiB|MiB|GiB|TiB)$")


class ConfigurationError(RuntimeError):
    """A setting needed for what's being done is missing (as opposed to set but invalid, which
    stops startup with a `ValidationError` when settings load)."""


class DataSource(NamedTuple):
    """Where pricing data is read from (018-app-cloud-deployment, data-model.md §1).

    `root` is a local directory for `local`, or `bucket[/prefix]` (no trailing slash) for `s3`.
    """

    kind: Literal["local", "s3"]
    root: str


def _parse_data_uri(value: str) -> DataSource:
    if value.startswith("/"):
        return DataSource("local", value)
    parsed = urlparse(value)
    if parsed.scheme == "file" and parsed.netloc == "" and parsed.path.startswith("/"):
        return DataSource("local", parsed.path)
    if parsed.scheme == "s3" and parsed.netloc:
        return DataSource("s3", f"{parsed.netloc}{parsed.path}".rstrip("/"))
    raise ValueError(
        "must be file:///absolute/path, /absolute/path or s3://bucket[/prefix] "
        "(the pipeline storage root)"
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost/cloud_pricing_dev"

    # 018-app-cloud-deployment (FR-001–FR-004): the pipeline storage root — a local directory or
    # s3://bucket[/prefix] — holding `aws/manifests/` and `aws/parquet/`. Snapshots are found only
    # through its manifests. Required by the web server (checked at startup through
    # `pricing_data_source`); the ops commands and Alembic don't need it.
    pricing_data_uri: str | None = None

    # Removed (FR-004). Declared only so that setting it, in the environment or `.env`, stops
    # startup with a message naming its replacement.
    aws_pricing_parquet_dir: str | None = Field(default=None, exclude=True)

    # 018 (FR-009–FR-011): the verified local copy of S3 snapshots. Unused for a local source.
    pricing_cache_dir: str = str(Path(tempfile.gettempdir()) / "cloud-pricing-cache")
    pricing_cache_max_bytes: int = Field(default=1073741824, ge=268435456)
    # Snapshots kept besides the active one.
    pricing_cache_keep: int = Field(default=1, ge=0)

    # 018 (research R3): fits DuckDB beside Postgres on a 2 GiB instance.
    duckdb_memory_limit: str = "512MB"
    duckdb_threads: int = Field(default=2, ge=1)

    # 018 (FR-021–FR-026): database backups (file:// or s3://) and the first-deploy owner password
    # (an SSM parameter name). Read by the `ops` commands; the backend only displays them.
    backup_uri: str | None = None
    backup_keep: int = Field(default=14, ge=1)
    owner_password_parameter: str | None = None

    # 018 (FR-044): alerts (backup failures, uptime, "up" notices) go to this SNS topic; unset
    # means they are only logged.
    alert_topic_arn: str | None = None
    uptime_alert_hours: int = Field(default=12, ge=1)
    uptime_alert_repeat_hours: int = Field(default=12, ge=1)

    # 018: shown in the Admin tab and recorded in backup metadata.
    app_environment: str = "local"
    app_release: str = "dev"

    # 018, local packaged stack only: `ops fetch-tls` copies the root from here instead of SSM.
    tls_root_dir: str | None = None

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

    @field_validator("pricing_data_uri")
    @classmethod
    def _valid_data_uri(cls, value: str | None) -> str | None:
        if value is None:
            return None
        source = _parse_data_uri(value)
        if source.kind == "local" and not Path(source.root).is_dir():
            raise ValueError(f"local directory {source.root} does not exist")
        return value

    @field_validator("backup_uri")
    @classmethod
    def _valid_backup_uri(cls, value: str | None) -> str | None:
        if value is not None and urlparse(value).scheme not in ("file", "s3"):
            raise ValueError("must be a file:// or s3:// location")
        return value

    @field_validator("duckdb_memory_limit")
    @classmethod
    def _valid_duckdb_size(cls, value: str) -> str:
        if not _DUCKDB_SIZE.match(value):
            raise ValueError("must be a DuckDB size such as 512MB or 1.5GiB")
        return value

    @model_validator(mode="after")
    def _old_data_setting_removed(self) -> Settings:
        if self.aws_pricing_parquet_dir is not None:
            raise ValueError(_OLD_DATA_SETTING_MESSAGE)
        return self

    @property
    def pricing_data_source(self) -> DataSource:
        """The parsed `PRICING_DATA_URI`. Raises `ConfigurationError` naming the setting when
        it's unset, so the web server refuses to start without a data source."""
        if self.pricing_data_uri is None:
            raise ConfigurationError(
                "PRICING_DATA_URI is not set. Set it to the pipeline storage root: "
                "file:///…/DATA/pipeline, /…/DATA/pipeline or s3://bucket[/prefix]."
            )
        return _parse_data_uri(self.pricing_data_uri)

    @model_validator(mode="after")
    def _catalog_search_default_within_max(self) -> Settings:
        if self.catalog_search_default_limit > self.catalog_search_max_limit:
            raise ValueError(
                "catalog_search_default_limit must not exceed catalog_search_max_limit"
            )
        return self


settings = Settings()
