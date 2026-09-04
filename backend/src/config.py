"""Application configuration.

Values come from environment variables (with sane local-dev defaults), never hardcoded
elsewhere, per the constitution's requirement that vendor pricing data access and the
Postgres connection be explicitly configured rather than assumed.
"""

from __future__ import annotations

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


settings = Settings()
