"""The verified local copy of S3 snapshots (018-app-cloud-deployment, FR-009–FR-011;
data-model.md §4, research.md R7). Constitution V: test-first.

A snapshot is downloaded into a temporary directory, every file checked against the manifest's
size and sha256, and only then renamed into place, so no reader ever sees a partial snapshot. A
verified entry is never downloaded again.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.pricing_data.manifest import Manifest
from src.pricing_data.snapshot_cache import (
    CacheError,
    ensure_cached,
    list_entries,
    startup_cleanup,
)
from src.pricing_data.storage import S3Store
from tests.helpers.fake_s3 import FakeS3Client, _error
from tests.helpers.parquet_tree import make_pipeline_root

GIB = 1024**3


def _bucket(tmp_path, snapshots):
    """Build a pipeline root on disk, then load every file into a fake bucket."""
    root = make_pipeline_root(tmp_path / "src", snapshots)
    client = FakeS3Client()
    for path in root.rglob("*"):
        if path.is_file():
            client.put("bucket", str(path.relative_to(root)), path.read_bytes())
    store = S3Store("bucket", client=client)
    return client, store


def _manifest(client, date: str) -> Manifest:
    key = f"aws/manifests/{date}/manifest.json"
    return Manifest.model_validate_json(client.objects[("bucket", key)])


def _free(n: int):
    return lambda _path: SimpleNamespace(free=n)


def test_fetch_writes_tmp_then_renames_to_date_and_revision(tmp_path):
    client, store = _bucket(tmp_path, [{"date": "2026-10-05", "revision": 2,
                                        "regions": ["us-east-1", "eu-west-1"]}])
    manifest = _manifest(client, "2026-10-05")
    cache = tmp_path / "cache"
    seen_tmp: list[str] = []

    original = store.download

    def watching_download(key, dest, expected_bytes, expected_sha256):
        seen_tmp.append(dest.parts[-len(key.split("/")) - 1])
        assert not (cache / "aws" / "2026-10-05-r2").exists()  # not visible while fetching
        original(key, dest, expected_bytes, expected_sha256)

    store.download = watching_download
    result = ensure_cached(store, manifest, cache, GIB, disk_free=_free(10 * GIB))

    entry = cache / "aws" / "2026-10-05-r2"
    assert result.path == entry
    assert result.manifest.revision == 2
    assert all(".tmp-" in name for name in seen_tmp)
    assert json.loads((entry / "cache-entry.json").read_text())["revision"] == 2
    for data_file in manifest.files():
        assert (entry / data_file.path).stat().st_size == data_file.bytes
    assert not list((cache / "aws").glob("*.tmp-*"))


@pytest.mark.parametrize("problem", ["sha", "size", "missing"])
def test_a_bad_or_missing_file_leaves_no_entry(tmp_path, problem):
    client, store = _bucket(tmp_path, [{"date": "2026-10-05"}])
    manifest = _manifest(client, "2026-10-05")
    victim = manifest.files()[3].path
    if problem == "sha":
        data = client.objects[("bucket", victim)]
        client.objects[("bucket", victim)] = data[:-1] + bytes([data[-1] ^ 0xFF])
    elif problem == "size":
        client.objects[("bucket", victim)] += b"extra"
    else:
        del client.objects[("bucket", victim)]
    cache = tmp_path / "cache"

    with pytest.raises(CacheError) as excinfo:
        ensure_cached(store, manifest, cache, GIB, disk_free=_free(10 * GIB))

    assert victim in str(excinfo.value)
    assert list((cache / "aws").iterdir()) == []


def test_a_verified_entry_is_never_downloaded_again(tmp_path):
    client, store = _bucket(tmp_path, [{"date": "2026-10-05"}])
    manifest = _manifest(client, "2026-10-05")
    cache = tmp_path / "cache"
    ensure_cached(store, manifest, cache, GIB, disk_free=_free(10 * GIB))
    client.calls.clear()

    again = ensure_cached(store, manifest, cache, GIB, disk_free=_free(10 * GIB))

    assert again.path == cache / "aws" / "2026-10-05-r1"
    assert client.calls == []


def test_startup_cleanup_deletes_leftover_tmp_directories(tmp_path):
    cache = tmp_path / "cache"
    (cache / "aws" / "2026-10-05-r1.tmp-abc123" / "aws").mkdir(parents=True)
    (cache / "aws" / "2026-10-04-r1").mkdir(parents=True)
    (cache / "aws" / "2026-10-04-r1" / "cache-entry.json").write_text("{}")
    startup_cleanup(cache)
    assert sorted(p.name for p in (cache / "aws").iterdir()) == ["2026-10-04-r1"]


def test_snapshot_over_the_size_limit_is_refused_without_download(tmp_path):
    client, store = _bucket(tmp_path, [{"date": "2026-10-05"}])
    manifest = _manifest(client, "2026-10-05")
    with pytest.raises(CacheError, match="PRICING_CACHE_MAX_BYTES"):
        ensure_cached(store, manifest, tmp_path / "cache", manifest.total_bytes - 1,
                      disk_free=_free(10 * GIB))
    assert not any(op == "GetObject" for op, _ in client.calls)


def test_snapshot_over_the_free_disk_space_is_refused_without_download(tmp_path):
    client, store = _bucket(tmp_path, [{"date": "2026-10-05"}])
    manifest = _manifest(client, "2026-10-05")
    with pytest.raises(CacheError, match="free"):
        ensure_cached(store, manifest, tmp_path / "cache", GIB,
                      disk_free=_free(manifest.total_bytes - 1))
    assert not any(op == "GetObject" for op, _ in client.calls)


def test_a_slow_fetch_rereads_the_manifest_and_restarts_on_a_new_revision(tmp_path):
    client, store = _bucket(tmp_path, [
        {"date": "2026-10-05", "revision": 1},
    ])
    rev1 = _manifest(client, "2026-10-05")
    # The pipeline publishes revision 2 of the same date while revision 1 is downloading.
    newer_root = make_pipeline_root(tmp_path / "newer", [{"date": "2026-10-05", "revision": 2}])
    for path in newer_root.rglob("*"):
        if path.is_file():
            client.put("bucket", str(path.relative_to(newer_root)), path.read_bytes())

    ticks = iter(range(0, 10_000, 100))  # every call advances the clock 100 s

    result = ensure_cached(
        store, rev1, tmp_path / "cache", GIB,
        clock=lambda: next(ticks), grace_seconds=300, disk_free=_free(10 * GIB),
    )

    assert result.manifest.revision == 2
    assert result.path.name == "2026-10-05-r2"
    assert not (tmp_path / "cache" / "aws" / "2026-10-05-r1").exists()


def test_a_listed_file_deleted_after_the_grace_period_restarts_with_the_new_manifest(tmp_path):
    client, store = _bucket(tmp_path, [{"date": "2026-10-05", "revision": 1}])
    rev1 = _manifest(client, "2026-10-05")
    newer_root = make_pipeline_root(tmp_path / "newer", [{"date": "2026-10-05", "revision": 2}])
    for path in newer_root.rglob("*"):
        if path.is_file():
            client.put("bucket", str(path.relative_to(newer_root)), path.read_bytes())
    # The pipeline already deleted revision 1's superseded files.
    for data_file in rev1.files():
        del client.objects[("bucket", data_file.path)]

    result = ensure_cached(store, rev1, tmp_path / "cache", GIB, disk_free=_free(10 * GIB))
    assert result.manifest.revision == 2


def test_other_s3_errors_are_reported(tmp_path):
    client, store = _bucket(tmp_path, [{"date": "2026-10-05"}])
    manifest = _manifest(client, "2026-10-05")

    def fail(operation, key):
        if key.endswith(".parquet"):
            raise _error("SlowDown", 503, operation)

    client.before_call = fail
    with pytest.raises(CacheError, match="SlowDown"):
        ensure_cached(store, manifest, tmp_path / "cache", GIB, disk_free=_free(10 * GIB))


def test_list_entries_reports_verified_entries(tmp_path):
    client, store = _bucket(tmp_path, [{"date": "2026-10-05"}])
    manifest = _manifest(client, "2026-10-05")
    cache = tmp_path / "cache"
    ensure_cached(store, manifest, cache, GIB, disk_free=_free(10 * GIB))
    (cache / "aws" / "2026-10-06-r1.tmp-zzz").mkdir()
    entries = list_entries(cache, "aws")
    assert [(e.snapshot_date, e.revision, e.bytes) for e in entries] == [
        ("2026-10-05", 1, manifest.total_bytes)
    ]
