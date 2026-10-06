"""No secret reaches the logs from the ops commands (018-app-cloud-deployment, FR-041, FR-050,
SC-013). db-init, backup and fetch-tls handle the owner password, the database password and the
TLS root key; none of them, nor a password hash, may appear in any log record."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest
from sqlalchemy.engine import make_url

from src.ops import alerts, params, tls
from src.ops.backup import run_backup
from src.ops.backup_store import open_backup_store
from src.ops.db_init import run_db_init
from tests.helpers.pg import require_pg_tools, scratch_database

OWNER_PASSWORD = "owner-S3cret-should-never-log"
DB_PASSWORD = "db-S3cret-should-never-log"


def test_ops_commands_log_no_secrets(tmp_path, monkeypatch, log_output):
    require_pg_tools()
    if shutil.which("openssl") is None:
        pytest.skip("openssl not on PATH")
    monkeypatch.setattr(alerts, "notify", lambda *a, **k: False)

    key = tmp_path / "root.key"
    cert = tmp_path / "root.crt"
    subprocess.run(["openssl", "ecparam", "-name", "prime256v1", "-genkey", "-noout",
                    "-out", str(key)], check=True, capture_output=True)
    subprocess.run(["openssl", "req", "-x509", "-new", "-key", str(key), "-days", "1",
                    "-subj", "/CN=t", "-out", str(cert)], check=True, capture_output=True)
    key_pem = key.read_text()
    secrets = {
        "/cloud-pricing-app/local/owner-password": OWNER_PASSWORD,
        "/cloud-pricing-app/local/tls/root-key": key_pem,
        "/cloud-pricing-app/local/tls/root-cert": cert.read_text(),
    }
    monkeypatch.setattr(params, "get_parameter", lambda name: secrets[name])
    monkeypatch.setattr(tls.settings, "tls_root_dir", None)
    monkeypatch.setattr(tls.settings, "app_environment", "local")

    store = open_backup_store(f"file://{tmp_path}/backups")
    with scratch_database(os.environ["DATABASE_URL"]) as url:
        # Trust auth ignores the password, but every command receives it in its URL.
        with_password = make_url(url).set(password=DB_PASSWORD).render_as_string(
            hide_password=False
        )
        run_db_init(database_url=with_password, store=store, backup_id=None,
                    owner_password_parameter="/cloud-pricing-app/local/owner-password",
                    allow_default_admin_password=False, result_path=tmp_path / "db-init.json")
        run_backup("manual", database_url=with_password, store=store, keep=3,
                   release="dev", environment="local")
    tls.fetch_tls(tmp_path / "tls")

    rendered = "\n".join(json.dumps(r) for r in log_output())
    assert "db-init finished" in rendered and "backup verified" in rendered
    for secret in (OWNER_PASSWORD, DB_PASSWORD, "pbkdf2_sha256$", "PRIVATE KEY",
                   key_pem.splitlines()[1]):
        assert secret not in rendered
    assert DB_PASSWORD not in (tmp_path / "db-init.json").read_text()
