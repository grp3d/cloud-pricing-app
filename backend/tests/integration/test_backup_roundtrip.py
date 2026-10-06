"""`ops backup` against a real Postgres (018-app-cloud-deployment, FR-025, FR-026, FR-044;
data-model.md §6, research.md R9). Constitution V: Postgres read/write of user data, test-first.

A backup is verified only after the stored object's size and checksum are re-read and
`pg_restore --list` accepts it. Retention runs only after a verified backup.
"""

from __future__ import annotations

import json
import os

import pytest

from src.ops import alerts
from src.ops.backup import run_backup
from src.ops.backup_store import open_backup_store
from src.ops.db import OpsError, alembic_upgrade, connect, libpq, run_tool, user_tables
from tests.helpers.pg import execute, require_pg_tools, scratch_database

TEST_DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture
def source_db():
    require_pg_tools()
    with scratch_database(TEST_DATABASE_URL) as url:
        alembic_upgrade(url)
        execute(
            url,
            "INSERT INTO users (id, username, password_hash, is_admin, is_active, "
            "is_default_admin) VALUES (gen_random_uuid(), 'alice', NULL, false, true, false)",
        )
        yield url


@pytest.fixture
def store(tmp_path):
    return open_backup_store(f"file://{tmp_path}/backups")


@pytest.fixture
def sent_alerts(monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(alerts, "notify", lambda message, subject=None: sent.append(message))
    return sent


def _backup(source_db, store, **kwargs):
    return run_backup(
        kwargs.pop("kind", "manual"),
        database_url=source_db,
        store=store,
        keep=kwargs.pop("keep", 14),
        release="v1.0.0",
        environment="local",
        **kwargs,
    )


def test_backup_produces_verified_metadata(source_db, store, sent_alerts):
    result = _backup(source_db, store)

    assert result["verified"] is True
    metadata = store.get(result["backup_id"])
    assert metadata["verified"] is True
    assert metadata["kind"] == "manual"
    assert metadata["environment"] == "local"
    assert metadata["app_release"] == "v1.0.0"
    assert metadata["alembic_revision"]
    # Every ORM table, from the metadata — not a hard-coded list.
    assert set(metadata["row_counts"]) == set(user_tables())
    assert metadata["row_counts"]["users"] == 2  # the seeded Admin and alice
    assert metadata["row_counts"]["architectures"] >= 1  # standard architectures seed
    assert (metadata["bytes"], metadata["sha256"]) == store.stat_dump(result["backup_id"])
    assert result["bytes"] == metadata["bytes"]
    assert sent_alerts == []


def test_restore_into_an_empty_database_reproduces_the_row_counts(source_db, store, tmp_path):
    result = _backup(source_db, store)
    metadata = store.get(result["backup_id"])
    dump = tmp_path / "restore.dump"
    store.fetch_dump(result["backup_id"], dump)

    with scratch_database(TEST_DATABASE_URL) as target:
        url, env = libpq(target)
        run_tool(["pg_restore", "--no-owner", "--exit-on-error", "-d", url, str(dump)], env)
        with connect(target) as conn:
            counts = {t: conn.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
                      for t in metadata["row_counts"]}
    assert counts == metadata["row_counts"]


def test_corrupted_dump_fails_verification_with_exit_4(source_db, store, sent_alerts):
    original = store._write

    def flip_a_byte(name, data):
        if name.endswith(".dump"):
            data = bytes([data[0] ^ 0xFF]) + data[1:]
        original(name, data)

    store._write = flip_a_byte
    with pytest.raises(OpsError) as excinfo:
        _backup(source_db, store)
    assert excinfo.value.code == 4
    assert all(m.get("verified") is not True for m in store.list_backups())
    assert len(sent_alerts) == 1
    assert "backup" in sent_alerts[0].lower()


def test_retention_runs_only_after_a_verified_backup(source_db, store, tmp_path):
    for stamp in ("20260101T000000Z", "20260102T000000Z", "20260103T000000Z"):
        backup_id = f"{stamp}-scheduled-v0.9.0"
        dump = tmp_path / "old.dump"
        dump.write_bytes(b"old")
        store.put_backup(backup_id, dump, {"id": backup_id, "verified": True})

    original = store._write

    def corrupt(name, data):
        original(name, data + b"!" if name.endswith(".dump") else data)

    store._write = corrupt
    with pytest.raises(OpsError):
        _backup(source_db, store, keep=1)
    assert len([m for m in store.list_backups() if m.get("verified")]) == 3

    store._write = original
    result = _backup(source_db, store, keep=1)
    remaining = [m["id"] for m in store.list_backups() if m.get("verified")]
    assert remaining == [result["backup_id"]]
    assert sorted(result["deleted"]) == sorted(
        f"{s}-scheduled-v0.9.0" for s in ("20260101T000000Z", "20260102T000000Z",
                                          "20260103T000000Z")
    )


def test_backup_metadata_is_written_after_the_dump(source_db, store, tmp_path):
    result = _backup(source_db, store)
    directory = store.directory
    dump = directory / f"{result['backup_id']}.dump"
    meta = directory / f"{result['backup_id']}.json"
    assert dump.stat().st_mtime_ns <= meta.stat().st_mtime_ns
    assert json.loads(meta.read_text())["id"] == result["backup_id"]
