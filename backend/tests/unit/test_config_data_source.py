"""Pricing data source and deployment settings (018-app-cloud-deployment, FR-001, FR-004,
FR-009–FR-011, FR-021–FR-026, FR-044; contracts/configuration.md).

`PRICING_DATA_URI` replaces `AWS_PRICING_PARQUET_DIR`: one setting naming the pipeline storage
root, either a local directory or `s3://`. An invalid value stops startup naming the setting; the
old setting stops startup naming its replacement.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import ConfigurationError, Settings

OLD_SETTING_MESSAGE = (
    "AWS_PRICING_PARQUET_DIR was replaced by PRICING_DATA_URI (the pipeline storage root, "
    "e.g. file:///…/DATA/pipeline). See docs/configuration.md."
)


def _settings() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture(autouse=True)
def _no_ambient_settings(monkeypatch):
    for name in ("PRICING_DATA_URI", "AWS_PRICING_PARQUET_DIR", "BACKUP_URI"):
        monkeypatch.delenv(name, raising=False)


# --- PRICING_DATA_URI -----------------------------------------------------------------------


def test_file_uri_is_a_local_source(monkeypatch, tmp_path):
    monkeypatch.setenv("PRICING_DATA_URI", f"file://{tmp_path}")
    source = _settings().pricing_data_source
    assert source.kind == "local"
    assert source.root == str(tmp_path)


def test_plain_absolute_path_is_a_local_source(monkeypatch, tmp_path):
    monkeypatch.setenv("PRICING_DATA_URI", str(tmp_path))
    source = _settings().pricing_data_source
    assert (source.kind, source.root) == ("local", str(tmp_path))


@pytest.mark.parametrize(
    ("uri", "root"),
    [
        ("s3://cloud-pricing-data-prod-g08a9i", "cloud-pricing-data-prod-g08a9i"),
        ("s3://bucket/some/prefix", "bucket/some/prefix"),
        ("s3://bucket/some/prefix/", "bucket/some/prefix"),
    ],
)
def test_s3_uri_is_an_s3_source(monkeypatch, uri, root):
    monkeypatch.setenv("PRICING_DATA_URI", uri)
    source = _settings().pricing_data_source
    assert (source.kind, source.root) == ("s3", root)


@pytest.mark.parametrize(
    "value",
    ["relative/path", "./data", "http://example.com/data", "", "s3://", "file://relative"],
)
def test_invalid_data_uri_stops_startup_naming_the_setting(monkeypatch, value):
    monkeypatch.setenv("PRICING_DATA_URI", value)
    with pytest.raises(ValidationError, match="pricing_data_uri"):
        _settings()


def test_missing_local_directory_stops_startup(monkeypatch, tmp_path):
    monkeypatch.setenv("PRICING_DATA_URI", f"file://{tmp_path / 'nope'}")
    with pytest.raises(ValidationError, match="does not exist"):
        _settings()


def test_unset_data_uri_fails_when_the_source_is_needed():
    settings = _settings()
    assert settings.pricing_data_uri is None
    with pytest.raises(ConfigurationError, match="PRICING_DATA_URI"):
        _ = settings.pricing_data_source


def test_old_setting_stops_startup_naming_its_replacement(monkeypatch, tmp_path):
    monkeypatch.setenv("PRICING_DATA_URI", str(tmp_path))
    monkeypatch.setenv("AWS_PRICING_PARQUET_DIR", "/anything")
    with pytest.raises(ValidationError) as excinfo:
        _settings()
    assert OLD_SETTING_MESSAGE in str(excinfo.value)


def test_old_setting_in_env_file_also_stops_startup(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(f"PRICING_DATA_URI={tmp_path}\nAWS_PRICING_PARQUET_DIR=/old\n")
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=str(env_file))
    assert OLD_SETTING_MESSAGE in str(excinfo.value)


# --- Cache and DuckDB -----------------------------------------------------------------------


def test_cache_defaults():
    settings = _settings()
    assert Path(settings.pricing_cache_dir).name == "cloud-pricing-cache"
    assert settings.pricing_cache_max_bytes == 1073741824
    assert settings.pricing_cache_keep == 1
    assert settings.duckdb_memory_limit == "512MB"
    assert settings.duckdb_threads == 2


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PRICING_CACHE_MAX_BYTES", "268435455"),
        ("PRICING_CACHE_KEEP", "-1"),
        ("DUCKDB_THREADS", "0"),
        ("DUCKDB_MEMORY_LIMIT", "lots"),
    ],
)
def test_cache_and_duckdb_bounds(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError, match=name.lower()):
        _settings()


def test_cache_minimums_are_accepted(monkeypatch):
    monkeypatch.setenv("PRICING_CACHE_MAX_BYTES", "268435456")
    monkeypatch.setenv("PRICING_CACHE_KEEP", "0")
    monkeypatch.setenv("DUCKDB_MEMORY_LIMIT", "1.5GiB")
    settings = _settings()
    assert settings.pricing_cache_max_bytes == 268435456
    assert settings.pricing_cache_keep == 0
    assert settings.duckdb_memory_limit == "1.5GiB"


# --- Database lifecycle, alerts, deployment identity ----------------------------------------


def test_lifecycle_defaults():
    settings = _settings()
    assert settings.backup_uri is None
    assert settings.backup_keep == 14
    assert settings.owner_password_parameter is None
    assert settings.alert_topic_arn is None
    assert settings.uptime_alert_hours == 12
    assert settings.uptime_alert_repeat_hours == 12
    assert settings.app_environment == "local"
    assert settings.app_release == "dev"
    assert settings.tls_root_dir is None


@pytest.mark.parametrize("value", ["file:///var/backups", "s3://bucket/prod/db/"])
def test_backup_uri_accepts_file_and_s3(monkeypatch, value):
    monkeypatch.setenv("BACKUP_URI", value)
    assert _settings().backup_uri == value


@pytest.mark.parametrize("value", ["/var/backups", "http://x/y", "gs://bucket/db"])
def test_backup_uri_rejects_other_schemes(monkeypatch, value):
    monkeypatch.setenv("BACKUP_URI", value)
    with pytest.raises(ValidationError, match="backup_uri"):
        _settings()


@pytest.mark.parametrize(
    ("name", "value"),
    [("BACKUP_KEEP", "0"), ("UPTIME_ALERT_HOURS", "0"), ("UPTIME_ALERT_REPEAT_HOURS", "0")],
)
def test_lifecycle_bounds(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError, match=name.lower()):
        _settings()


def test_environment_and_release_read_env(monkeypatch):
    monkeypatch.setenv("APP_ENVIRONMENT", "prod")
    monkeypatch.setenv("APP_RELEASE", "v1.4.0")
    settings = _settings()
    assert (settings.app_environment, settings.app_release) == ("prod", "v1.4.0")
