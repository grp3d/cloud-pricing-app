"""`ops db-init`: restore or initialize, then migrate (018-app-cloud-deployment, FR-021–FR-024;
research.md R8, contracts/ops-cli.md). Constitution V: Postgres read/write, test-first.

An empty database is restored from the newest verified backup, or the named one, or created
fresh. A backup that can't be restored or verified fails the bring-up and never leaves a
half-initialized database. The owner password is set only on a fresh database.
"""

from __future__ import annotations

import json
import os

import pytest
from alembic import command

from src.ops import alerts, db_init, params
from src.ops.backup import run_backup
from src.ops.backup_store import open_backup_store
from src.ops.db import (
    OpsError,
    _alembic_config,
    alembic_revision,
    alembic_upgrade,
    connect,
    known_revisions,
)
from src.ops.db_init import run_db_init
from src.services.auth_service import hash_password, verify_password
from tests.helpers.pg import execute, require_pg_tools, scratch_database

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
OWNER_PARAMETER = "/cloud-pricing-app/test/owner-password"
OWNER_PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
def _quiet_alerts(monkeypatch):
    monkeypatch.setattr(alerts, "notify", lambda *a, **k: False)


@pytest.fixture
def owner_parameter(monkeypatch):
    reads: list[str] = []

    def fake_get_parameter(name: str) -> str:
        reads.append(name)
        if name != OWNER_PARAMETER:
            raise KeyError(name)
        return OWNER_PASSWORD

    monkeypatch.setattr(params, "get_parameter", fake_get_parameter)
    return reads


@pytest.fixture
def store(tmp_path):
    return open_backup_store(f"file://{tmp_path}/backups")


@pytest.fixture
def target():
    with scratch_database(TEST_DATABASE_URL) as url:
        yield url


@pytest.fixture
def backed_up(store):
    """A source database with one extra user, backed up twice (an older and a newer backup)."""
    require_pg_tools()
    with scratch_database(TEST_DATABASE_URL) as source:
        alembic_upgrade(source)
        execute(
            source,
            "INSERT INTO users (id, username, is_admin, is_active, is_default_admin) "
            "VALUES (gen_random_uuid(), 'alice', false, true, false)",
        )
        older = run_backup("scheduled", database_url=source, store=store, keep=14,
                           release="v1.0.0", environment="test")
        execute(
            source,
            "INSERT INTO users (id, username, is_admin, is_active, is_default_admin) "
            "VALUES (gen_random_uuid(), 'bob', false, true, false)",
        )
        from datetime import UTC, datetime, timedelta

        newer = run_backup("scheduled", database_url=source, store=store, keep=14,
                           release="v1.0.0", environment="test",
                           now=datetime.now(UTC) + timedelta(seconds=5))
        yield {"older": older["backup_id"], "newer": newer["backup_id"]}


def _init(target, store, tmp_path, **kwargs):
    return run_db_init(
        database_url=target,
        store=store,
        backup_id=kwargs.pop("backup_id", None),
        owner_password_parameter=kwargs.pop("owner_password_parameter", OWNER_PARAMETER),
        allow_default_admin_password=kwargs.pop("allow_default_admin_password", False),
        result_path=tmp_path / "db-init.json",
    )


def _usernames(url) -> set[str]:
    return {r[0] for r in execute(url, "SELECT username FROM users WHERE username IS NOT NULL")}


def _admin_hash(url) -> str:
    return execute(url, "SELECT password_hash FROM users WHERE is_default_admin")[0][0]


def _has_alembic_version(url) -> bool:
    with connect(url) as conn:
        return alembic_revision(conn) is not None


# --- fresh ------------------------------------------------------------------------------------


def test_empty_database_with_no_backups_is_fresh_with_owner_password(
    target, store, tmp_path, owner_parameter
):
    result = _init(target, store, tmp_path)

    assert result["db"] == "fresh"
    assert result["backup_id"] is None
    assert _has_alembic_version(target)
    admin_hash = _admin_hash(target)
    assert verify_password(OWNER_PASSWORD, admin_hash)
    assert not verify_password("admin123", admin_hash)
    assert owner_parameter == [OWNER_PARAMETER]
    written = json.loads((tmp_path / "db-init.json").read_text())
    assert written["db"] == "fresh"


def test_fresh_database_without_owner_password_refuses(target, store, tmp_path, owner_parameter):
    with pytest.raises(OpsError) as excinfo:
        _init(target, store, tmp_path, owner_password_parameter=None)
    assert excinfo.value.code == 3
    assert not _has_alembic_version(target)
    assert json.loads((tmp_path / "db-init.json").read_text())["db"] == "failed"


def test_fresh_database_may_keep_default_password_when_allowed(target, store, tmp_path):
    result = _init(target, store, tmp_path, owner_password_parameter=None,
                   allow_default_admin_password=True)
    assert result["db"] == "fresh"
    assert verify_password("admin123", _admin_hash(target))


def test_unset_backup_location_refuses(target, tmp_path, owner_parameter):
    with pytest.raises(OpsError) as excinfo:
        _init(target, None, tmp_path)
    assert excinfo.value.code == 3


# --- restore ----------------------------------------------------------------------------------


def test_empty_database_restores_newest_verified_backup(
    target, store, tmp_path, backed_up, owner_parameter
):
    result = _init(target, store, tmp_path)

    assert result["db"] == "restored"
    assert result["backup_id"] == backed_up["newer"]
    assert {"alice", "bob"} <= _usernames(target)
    assert result["row_counts"] == store.get(backed_up["newer"])["row_counts"]
    # The restored Admin keeps its own password; the owner parameter is never read.
    assert owner_parameter == []
    assert verify_password("admin123", _admin_hash(target))


def test_named_backup_is_restored(target, store, tmp_path, backed_up, owner_parameter):
    result = _init(target, store, tmp_path, backup_id=backed_up["older"])
    assert result["backup_id"] == backed_up["older"]
    names = _usernames(target)
    assert "alice" in names and "bob" not in names


def test_named_backup_that_does_not_exist_refuses(target, store, tmp_path, backed_up):
    with pytest.raises(OpsError) as excinfo:
        _init(target, store, tmp_path, backup_id="20200101T000000Z-manual-v0")
    assert excinfo.value.code == 3
    assert not _has_alembic_version(target)


def test_row_count_mismatch_fails_with_exit_4_and_leaves_database_empty(
    target, store, tmp_path, backed_up
):
    metadata = store.get(backed_up["newer"])
    metadata["row_counts"]["users"] += 1
    store.write_metadata(backed_up["newer"], metadata)

    with pytest.raises(OpsError) as excinfo:
        _init(target, store, tmp_path)
    assert excinfo.value.code == 4
    assert backed_up["newer"] in str(excinfo.value)
    # Not half-initialized: a rerun must not mistake it for an existing database.
    assert not _has_alembic_version(target)
    assert execute(target, "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'") == [(0,)]


def test_corrupt_dump_fails_with_exit_4(target, store, tmp_path, backed_up):
    dump = store.directory / f"{backed_up['newer']}.dump"
    data = dump.read_bytes()
    dump.write_bytes(data[:-1] + bytes([data[-1] ^ 0xFF]))
    with pytest.raises(OpsError) as excinfo:
        _init(target, store, tmp_path)
    assert excinfo.value.code == 4
    assert not _has_alembic_version(target)


def test_backup_from_a_newer_release_refuses_with_exit_3(target, store, tmp_path, backed_up):
    metadata = store.get(backed_up["newer"])
    metadata["alembic_revision"] = "9999_from_the_future"
    store.write_metadata(backed_up["newer"], metadata)
    with pytest.raises(OpsError, match="newer release") as excinfo:
        _init(target, store, tmp_path)
    assert excinfo.value.code == 3
    assert not _has_alembic_version(target)


def test_backup_from_an_older_release_is_restored_then_migrated(
    target, store, tmp_path, owner_parameter
):
    # v0.0.1's backups are at 0005: tables added later (0006+) aren't in the dump, so the
    # restore check must count only what the backup has, and the migrations then add the rest.
    require_pg_tools()
    rev_0005 = "7c2e9d41b8a3"
    with scratch_database(TEST_DATABASE_URL) as source:
        command.upgrade(_alembic_config(source), rev_0005)
        execute(
            source,
            "INSERT INTO users (id, username, is_admin, is_active, is_default_admin) "
            "VALUES (gen_random_uuid(), 'alice', false, true, false)",
        )
        old = run_backup("scheduled", database_url=source, store=store, keep=14,
                         release="v0.0.1", environment="test")
    assert "service_category_rules" not in store.get(old["backup_id"])["row_counts"]

    result = _init(target, store, tmp_path)

    assert result["db"] == "restored"
    assert result["backup_id"] == old["backup_id"]
    assert "alice" in _usernames(target)
    with connect(target) as conn:
        head = alembic_revision(conn)
    assert head in known_revisions() and head != rev_0005
    assert "service_category_rules" in result["row_counts"]


def test_an_unexpected_error_is_still_written_as_failed(target, store, tmp_path, monkeypatch):
    # The health check waits for this file; without it a crash looks like "not finished yet"
    # and the bring-up only fails after its 10-minute wait.
    def boom(_url):
        raise RuntimeError("migration exploded")

    monkeypatch.setattr(db_init, "alembic_upgrade", boom)
    with pytest.raises(RuntimeError):
        _init(target, store, tmp_path, owner_password_parameter=None,
              allow_default_admin_password=True)
    written = json.loads((tmp_path / "db-init.json").read_text())
    assert written["db"] == "failed"
    assert "migration exploded" in written["error"]


# --- existing ---------------------------------------------------------------------------------


def test_existing_database_is_only_migrated(target, store, tmp_path, backed_up, owner_parameter):
    alembic_upgrade(target)
    custom = hash_password("changed in the app")
    execute(target, "UPDATE users SET password_hash = %s WHERE is_default_admin", (custom,))

    result = _init(target, store, tmp_path)

    assert result["db"] == "existing"
    assert result["backup_id"] is None
    assert _admin_hash(target) == custom
    assert owner_parameter == []
    assert "alice" not in _usernames(target)  # nothing was restored over it
