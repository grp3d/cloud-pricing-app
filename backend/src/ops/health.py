"""`ops health [--wait SECONDS]` — is the app healthy? (018-app-cloud-deployment, FR-028;
contracts/ops-cli.md, research.md R11).

Run on the instance through SSM by `deploy/app up` (the runner can't reach the app, which only
answers allowlisted addresses). Healthy means: `db-init` succeeded, the backend's `/health`
answers, the default Admin account exists and is active, and the login endpoint rejects an
unknown user. It never uses the owner password, which the owner may have changed in the app.
Missing pricing is still healthy, with the reason (Story 2 AS4).
"""

from __future__ import annotations

import json
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path

from src.config import settings
from src.logging_config import get_logger
from src.ops.db import connect

logger = get_logger("cloud_pricing.ops.health")

BACKEND_URL = "http://backend:8000"
_POLL_SECONDS = 5


def _now() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _get_health() -> dict | None:
    """The backend's /health body, or None while it doesn't answer."""
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}/health", timeout=5) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _login_status(username: str) -> int:
    request = urllib.request.Request(
        f"{BACKEND_URL}/api/v1/auth/login",
        data=json.dumps({"username": username, "password": secrets.token_hex(16)}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError):
        return 0


def _admin_row() -> tuple[bool] | None:
    with connect(settings.database_url) as conn:
        return conn.execute("SELECT is_active FROM users WHERE is_default_admin").fetchone()


def _read_db_init(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _check(db_init_result: Path) -> tuple[bool | None, dict]:
    """(True healthy | False definitely unhealthy | None not ready yet, details)."""
    db_init = _read_db_init(db_init_result)
    if db_init is None:
        return None, {"db": None, "reason": "db-init has not finished"}
    db_state = db_init.get("db")
    if db_state == "failed":
        return False, {"db": "failed", "reason": f"db-init failed: {db_init.get('error')}"}
    body = _get_health()
    if body is None:
        return None, {"db": db_state, "reason": "the backend is not answering yet"}
    details = {
        "db": db_state,
        "pricing": body.get("pricing", "unavailable"),
        "pricing_reason": body.get("pricing_reason"),
    }
    try:
        admin = _admin_row()
    except Exception as exc:  # noqa: BLE001 — reported, not raised
        return None, {**details, "reason": f"database check failed: {exc}"}
    if admin is None or admin[0] is not True:
        return False, {**details, "reason": "the default Admin account is missing or inactive"}
    status = _login_status(f"health-{secrets.token_hex(8)}")
    if status != 401:
        return False, {**details, "reason": f"login did not reject an unknown user (HTTP {status})"}
    return True, details


def run_health(*, wait_seconds: int, db_init_result: Path) -> dict:
    deadline = _now() + wait_seconds
    while True:
        verdict, details = _check(db_init_result)
        if verdict is not None:
            break
        if _now() >= deadline:
            details["reason"] = f"timed out after {wait_seconds}s: {details['reason']}"
            verdict = False
            break
        _sleep(_POLL_SECONDS)
    result = {
        "healthy": verdict,
        "db": details.get("db"),
        "pricing": details.get("pricing", "unavailable"),
        "pricing_reason": details.get("pricing_reason"),
        "release": settings.app_release,
    }
    if not verdict:
        result["reason"] = details.get("reason")
    logger.info("health checked", **{k: v for k, v in result.items() if k != "release"})
    return result
