"""Settings validation (016-canvas-icon-layout, FR-015/FR-018/FR-025–FR-026): every operational
value is a named setting with today's behavior as its default, overridable by an environment
variable, and an invalid value stops startup with an error naming the setting."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from src.config import Settings


def _settings() -> Settings:
    return Settings(_env_file=None)


def test_snapshot_check_interval_defaults_to_five_minutes():
    assert _settings().snapshot_check_interval_seconds == 300


def test_snapshot_check_interval_reads_env(monkeypatch):
    monkeypatch.setenv("SNAPSHOT_CHECK_INTERVAL_SECONDS", "60")
    assert _settings().snapshot_check_interval_seconds == 60


@pytest.mark.parametrize("value", ["abc", "5"])
def test_snapshot_check_interval_rejects_invalid(monkeypatch, value):
    monkeypatch.setenv("SNAPSHOT_CHECK_INTERVAL_SECONDS", value)
    with pytest.raises(ValidationError, match="snapshot_check_interval_seconds"):
        _settings()


def test_active_snapshot_date_defaults_to_none():
    assert _settings().active_snapshot_date is None


def test_active_snapshot_date_reads_env(monkeypatch):
    monkeypatch.setenv("ACTIVE_SNAPSHOT_DATE", "2026-09-20")
    assert _settings().active_snapshot_date == date(2026, 9, 20)


def test_active_snapshot_date_rejects_invalid(monkeypatch):
    monkeypatch.setenv("ACTIVE_SNAPSHOT_DATE", "not-a-date")
    with pytest.raises(ValidationError, match="active_snapshot_date"):
        _settings()


# --- 016-canvas-icon-layout, US8 (FR-025–FR-026): the remaining hard-coded values ------------


def test_cors_allowed_origins_default_and_env(monkeypatch):
    assert _settings().cors_allowed_origins == ["http://localhost:5173"]
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["http://a","http://b"]')
    assert _settings().cors_allowed_origins == ["http://a", "http://b"]


def test_catalog_search_limits_default_and_validation(monkeypatch):
    settings = _settings()
    assert settings.catalog_search_default_limit == 50
    assert settings.catalog_search_max_limit == 200
    monkeypatch.setenv("CATALOG_SEARCH_DEFAULT_LIMIT", "300")
    with pytest.raises(ValidationError, match="catalog_search"):
        _settings()


def test_password_hash_iterations_default_and_minimum(monkeypatch):
    assert _settings().password_hash_iterations == 260_000
    monkeypatch.setenv("PASSWORD_HASH_ITERATIONS", "1000")
    with pytest.raises(ValidationError, match="password_hash_iterations"):
        _settings()


def test_log_level_default_and_validation(monkeypatch):
    assert _settings().log_level == "INFO"
    monkeypatch.setenv("LOG_LEVEL", "LOUD")
    with pytest.raises(ValidationError, match="log_level"):
        _settings()


# --- 017-structured-json-logging, FR-001a: LOG_FORMAT ----------------------------------------


def test_log_format_defaults_to_json():
    assert _settings().log_format == "json"


def test_log_format_reads_env(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "console")
    assert _settings().log_format == "console"


def test_log_format_rejects_invalid(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "xml")
    with pytest.raises(ValidationError, match="log_format"):
        _settings()


def test_changing_iterations_keeps_existing_passwords_valid(monkeypatch):
    from src.services import auth_service

    monkeypatch.setattr(auth_service.settings, "password_hash_iterations", 260_000)
    stored = auth_service.hash_password("s3cret-pass")
    assert "$260000$" in stored
    monkeypatch.setattr(auth_service.settings, "password_hash_iterations", 300_000)
    assert "$300000$" in auth_service.hash_password("s3cret-pass")
    assert auth_service.verify_password("s3cret-pass", stored)
