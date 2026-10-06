"""Backup objects on `file://` and `s3://` (018-app-cloud-deployment, FR-025, FR-026;
data-model.md §6, contracts/ops-cli.md).

A backup is `<id>.dump` plus `<id>.json`, the metadata written last. A dump without its
metadata is incomplete and never chosen for a restore.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest

from src.ops.backup_store import BackupStore, make_backup_id, open_backup_store
from tests.helpers.fake_s3 import FakeS3Client

BUCKET = "cloud-pricing-app-backups-test"


@pytest.fixture(params=["file", "s3"])
def store(request, tmp_path) -> BackupStore:
    if request.param == "file":
        return open_backup_store(f"file://{tmp_path}/backups")
    return open_backup_store(f"s3://{BUCKET}/prod/db/", client=FakeS3Client())


def _dump(tmp_path, content: bytes = b"PGDMP fake dump"):
    path = tmp_path / "x.dump"
    path.write_bytes(content)
    return path


def _metadata(backup_id: str, *, verified: bool, created_at: str) -> dict:
    return {
        "id": backup_id,
        "kind": backup_id.split("-")[1],
        "created_at": created_at,
        "verified": verified,
        "app_release": "v1.0.0",
    }


def test_backup_id_format():
    now = datetime(2026, 10, 5, 14, 3, 9, tzinfo=UTC)
    assert make_backup_id("teardown", "v1.4.0", now) == "20261005T140309Z-teardown-v1.4.0"


def test_put_backup_writes_dump_before_metadata(store, tmp_path):
    order: list[str] = []
    original = store._write

    def recording_write(name, data):
        order.append(name.rsplit(".", 1)[1])
        original(name, data)

    store._write = recording_write
    backup_id = "20261005T140309Z-manual-dev"
    store.put_backup(backup_id, _dump(tmp_path), _metadata(backup_id, verified=False,
                                                          created_at="2026-10-05T14:03:09Z"))
    assert order == ["dump", "json"]
    assert store.get(backup_id)["id"] == backup_id


def test_list_ignores_dump_without_metadata(store, tmp_path):
    store._write("20261005T140309Z-manual-dev.dump", b"orphan")
    backup_id = "20261004T000000Z-scheduled-dev"
    store.put_backup(backup_id, _dump(tmp_path), _metadata(backup_id, verified=True,
                                                          created_at="2026-10-04T00:00:00Z"))
    assert [b["id"] for b in store.list_backups()] == [backup_id]
    assert store.list_orphan_dumps() == ["20261005T140309Z-manual-dev"]


def test_list_is_newest_first_and_newest_verified_skips_unverified(store, tmp_path):
    for backup_id, verified in [
        ("20261001T000000Z-scheduled-dev", True),
        ("20261003T000000Z-scheduled-dev", True),
        ("20261004T000000Z-manual-dev", False),
    ]:
        created = f"{backup_id[:4]}-{backup_id[4:6]}-{backup_id[6:8]}T00:00:00Z"
        store.put_backup(backup_id, _dump(tmp_path),
                         _metadata(backup_id, verified=verified, created_at=created))
    assert [b["id"] for b in store.list_backups()] == [
        "20261004T000000Z-manual-dev",
        "20261003T000000Z-scheduled-dev",
        "20261001T000000Z-scheduled-dev",
    ]
    assert store.newest_verified()["id"] == "20261003T000000Z-scheduled-dev"
    assert store.get("20261001T000000Z-scheduled-dev")["verified"] is True
    assert store.get("missing") is None


def test_newest_verified_is_none_when_empty(store):
    assert store.newest_verified() is None
    assert store.list_backups() == []


def test_stat_dump_reports_size_and_sha(store, tmp_path):
    content = b"PGDMP" + bytes(range(256)) * 10
    backup_id = "20261005T000000Z-manual-dev"
    store.put_backup(backup_id, _dump(tmp_path, content),
                     _metadata(backup_id, verified=False, created_at="2026-10-05T00:00:00Z"))
    assert store.stat_dump(backup_id) == (len(content), hashlib.sha256(content).hexdigest())


def test_fetch_dump_round_trips(store, tmp_path):
    content = b"PGDMP round trip"
    backup_id = "20261005T000000Z-manual-dev"
    store.put_backup(backup_id, _dump(tmp_path, content),
                     _metadata(backup_id, verified=True, created_at="2026-10-05T00:00:00Z"))
    dest = tmp_path / "out" / "restore.dump"
    store.fetch_dump(backup_id, dest)
    assert dest.read_bytes() == content


def test_update_metadata_and_delete(store, tmp_path):
    backup_id = "20261005T000000Z-manual-dev"
    store.put_backup(backup_id, _dump(tmp_path),
                     _metadata(backup_id, verified=False, created_at="2026-10-05T00:00:00Z"))
    metadata = store.get(backup_id)
    metadata["verified"] = True
    store.write_metadata(backup_id, metadata)
    assert store.get(backup_id)["verified"] is True
    store.delete(backup_id)
    assert store.get(backup_id) is None
    assert store.list_orphan_dumps() == []


def test_s3_metadata_is_json_under_the_prefix(tmp_path):
    client = FakeS3Client()
    store = open_backup_store(f"s3://{BUCKET}/prod/db/", client=client)
    backup_id = "20261005T000000Z-manual-dev"
    store.put_backup(backup_id, _dump(tmp_path),
                     _metadata(backup_id, verified=False, created_at="2026-10-05T00:00:00Z"))
    assert client.keys(BUCKET) == [f"prod/db/{backup_id}.dump", f"prod/db/{backup_id}.json"]
    assert json.loads(client.objects[(BUCKET, f"prod/db/{backup_id}.json")])["id"] == backup_id


@pytest.mark.parametrize("uri", ["/plain/path", "gs://bucket/db", "s3://"])
def test_open_backup_store_rejects_bad_uris(uri):
    with pytest.raises(ValueError):
        open_backup_store(uri)
