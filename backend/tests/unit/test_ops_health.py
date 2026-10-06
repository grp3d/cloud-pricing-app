"""`ops health` (018-app-cloud-deployment, FR-028; contracts/ops-cli.md, Story 2 AS3–AS4).

"Healthy" means db-init succeeded, the backend answers, the default Admin account exists and is
active, and the login endpoint rejects an unknown user. It never uses the owner password, which
the owner may have changed in the app. Missing pricing is healthy with a reason.
"""

from __future__ import annotations

import json

import pytest

from src.ops import health, params


@pytest.fixture
def db_init(tmp_path):
    path = tmp_path / "db-init.json"

    def write(result: dict) -> None:
        path.write_text(json.dumps(result))

    write({"db": "restored", "backup_id": "x", "alembic_revision": "0005", "row_counts": {}})
    return path, write


class Probe:
    """Stubbed checks: the backend's /health, the login probe and the Admin row."""

    def __init__(self) -> None:
        self.health: dict | None = {"status": "ok", "pricing": "ok", "pricing_reason": None}
        self.login_status = 401
        self.admin: tuple[bool] | None = (True,)
        self.login_usernames: list[str] = []

    def get_health(self) -> dict | None:
        return self.health

    def login_status_for(self, username: str) -> int:
        self.login_usernames.append(username)
        return self.login_status

    def admin_row(self) -> tuple[bool] | None:
        return self.admin


@pytest.fixture
def probe(monkeypatch):
    p = Probe()
    monkeypatch.setattr(health, "_get_health", p.get_health)
    monkeypatch.setattr(health, "_login_status", p.login_status_for)
    monkeypatch.setattr(health, "_admin_row", p.admin_row)
    monkeypatch.setattr(health, "_sleep", lambda _s: None)
    monkeypatch.setattr(params, "get_parameter", lambda name: pytest.fail("never reads secrets"))
    return p


def test_healthy_with_pricing(db_init, probe):
    result = health.run_health(wait_seconds=0, db_init_result=db_init[0])
    assert result["healthy"] is True
    assert result["db"] == "restored"
    assert result["pricing"] == "ok"
    assert result["pricing_reason"] is None
    assert "release" in result


def test_healthy_without_pricing_carries_the_reason(db_init, probe):
    probe.health = {"status": "ok", "pricing": "unavailable",
                    "pricing_reason": "no snapshot available"}
    result = health.run_health(wait_seconds=0, db_init_result=db_init[0])
    assert result["healthy"] is True
    assert result["pricing"] == "unavailable"
    assert result["pricing_reason"] == "no snapshot available"


def test_a_changed_admin_password_does_not_matter(db_init, probe):
    # Nothing about the Admin's password is consulted: the login probe uses a random username.
    result = health.run_health(wait_seconds=0, db_init_result=db_init[0])
    assert result["healthy"] is True
    assert all(name not in ("Admin", "admin") for name in probe.login_usernames)
    assert len(set(probe.login_usernames)) == len(probe.login_usernames)


@pytest.mark.parametrize("admin", [None, (False,)], ids=["missing", "inactive"])
def test_unhealthy_without_an_active_admin(db_init, probe, admin):
    probe.admin = admin
    result = health.run_health(wait_seconds=0, db_init_result=db_init[0])
    assert result["healthy"] is False
    assert "Admin" in result["reason"]


@pytest.mark.parametrize("status", [200, 500, 503])
def test_unhealthy_when_login_does_not_reject_an_unknown_user(db_init, probe, status):
    probe.login_status = status
    result = health.run_health(wait_seconds=0, db_init_result=db_init[0])
    assert result["healthy"] is False
    assert "login" in result["reason"]


def test_unhealthy_when_db_init_failed_with_its_error(db_init, probe):
    path, write = db_init
    write({"db": "failed", "error": "backup 2026… failed row-count verification", "exit_code": 4})
    result = health.run_health(wait_seconds=600, db_init_result=path)
    assert result["healthy"] is False
    assert result["db"] == "failed"
    assert "row-count" in result["reason"]


def test_wait_times_out_unhealthy(tmp_path, probe, monkeypatch):
    ticks = iter(range(0, 10_000, 30))
    monkeypatch.setattr(health, "_now", lambda: next(ticks))
    probe.health = None  # the backend never answers
    result = health.run_health(wait_seconds=120, db_init_result=tmp_path / "missing.json")
    assert result["healthy"] is False
    assert "timed out" in result["reason"]


def test_wait_succeeds_once_everything_is_up(db_init, probe, monkeypatch):
    answers = iter([None, None, {"status": "ok", "pricing": "ok", "pricing_reason": None}])
    monkeypatch.setattr(health, "_get_health", lambda: next(answers))
    result = health.run_health(wait_seconds=600, db_init_result=db_init[0])
    assert result["healthy"] is True
