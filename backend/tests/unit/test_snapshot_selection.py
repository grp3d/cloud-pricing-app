"""Choosing the snapshot to use (018-app-cloud-deployment, FR-004–FR-008; data-model.md §2–3,
research.md R7). Constitution V: selection of pricing data is test-first.

Snapshots are found only through manifests: `latest.json` for the newest, or the pinned date's
manifest. A missing pointer (including S3's AccessDenied for a missing key) means "no snapshot
yet", not an error. A bad pin or the old layout stops startup with a message saying what to do.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from src.pricing_data.active_snapshot import (
    ActiveSnapshotConfigError,
    previous_snapshot,
    select_snapshot,
)
from src.pricing_data.storage import LocalStore, S3Store
from tests.helpers.fake_s3 import FakeS3Client
from tests.helpers.parquet_tree import make_pipeline_root, make_snapshot_tree


def _root(tmp_path, snapshots):
    return LocalStore(make_pipeline_root(tmp_path, snapshots))


def test_newest_snapshot_comes_from_latest_json(tmp_path):
    store = _root(tmp_path, [
        {"date": "2026-10-01"},
        {"date": "2026-10-05", "point_latest": True},
        {"date": "2026-10-09", "status": "partial", "failed_regions": [("us-east-1", "x")]},
    ])
    selection = select_snapshot(store, "aws", None, at_startup=True)
    assert selection.manifest.snapshot_date == "2026-10-05"
    assert selection.rejected is None
    assert selection.pinned is False


def test_pin_selects_that_dates_manifest(tmp_path):
    store = _root(tmp_path, [{"date": "2026-10-01"}, {"date": "2026-10-05", "point_latest": True}])
    selection = select_snapshot(store, "aws", date(2026, 10, 1), at_startup=True)
    assert selection.manifest.snapshot_date == "2026-10-01"
    assert selection.pinned is True


@pytest.mark.parametrize(
    "spec",
    [
        {"date": "2026-10-01", "status": "purged"},
        {"date": "2026-10-01", "status": "partial", "failed_regions": [("us-east-1", "x")]},
        None,
    ],
    ids=["purged", "partial", "missing"],
)
def test_unusable_pin_stops_startup(tmp_path, spec):
    snapshots = [{"date": "2026-10-05", "point_latest": True}] + ([spec] if spec else [])
    store = _root(tmp_path, snapshots)
    with pytest.raises(ActiveSnapshotConfigError, match="ACTIVE_SNAPSHOT_DATE=2026-10-01"):
        select_snapshot(store, "aws", date(2026, 10, 1), at_startup=True)


def test_unusable_pin_after_startup_is_a_rejection_not_a_crash(tmp_path):
    store = _root(tmp_path, [{"date": "2026-10-01", "status": "purged"}])
    selection = select_snapshot(store, "aws", date(2026, 10, 1), at_startup=False)
    assert selection.manifest is None
    assert "purged" in selection.rejected.reason


def test_missing_latest_json_means_no_snapshot_available(tmp_path):
    store = _root(tmp_path, [{"date": "2026-10-05"}])  # no pointer yet
    selection = select_snapshot(store, "aws", None, at_startup=True)
    assert selection.manifest is None
    assert selection.rejected is None
    assert selection.reason == "no snapshot available"


def test_s3_access_denied_for_a_missing_pointer_means_no_snapshot_available():
    store = S3Store("bucket", client=FakeS3Client(deny_missing=True))
    selection = select_snapshot(store, "aws", None, at_startup=True)
    assert selection.manifest is None
    assert selection.reason == "no snapshot available"


def test_rejected_manifest_is_reported(tmp_path):
    store = _root(tmp_path, [{"date": "2026-10-05", "point_latest": True,
                              "schema_versions": {"price_fact": 2}}])
    selection = select_snapshot(store, "aws", None, at_startup=True)
    assert selection.manifest is None
    assert selection.rejected.snapshot_date == "2026-10-05"
    assert "schema version 2" in selection.rejected.reason


def test_manifest_revision_below_the_pointer_is_rejected(tmp_path):
    root = make_pipeline_root(
        tmp_path, [{"date": "2026-10-05", "revision": 1, "point_latest": True}]
    )
    latest = root / "aws/manifests/latest.json"
    pointer = json.loads(latest.read_text())
    pointer["revision"] = 2
    latest.write_text(json.dumps(pointer))
    selection = select_snapshot(LocalStore(root), "aws", None, at_startup=True)
    assert "revision 1 is lower" in selection.rejected.reason


def test_old_layout_directory_stops_startup_with_conversion_instructions(tmp_path):
    make_snapshot_tree(tmp_path, {"2026-09-24": {}})
    with pytest.raises(ActiveSnapshotConfigError) as excinfo:
        select_snapshot(LocalStore(tmp_path), "aws", None, at_startup=True)
    message = str(excinfo.value)
    assert "old layout" in message
    assert "upload-history" in message


def test_bad_paths_are_rejected_before_any_data_file_is_read():
    client = FakeS3Client()
    manifest = json.loads(open("tests/fixtures/manifests/bad_path_dotdot.json").read())
    client.put("bucket", "aws/manifests/2026-10-05/manifest.json", json.dumps(manifest).encode())
    client.put("bucket", "aws/manifests/latest.json", json.dumps({
        "manifest_version": "1.0", "provider": "aws", "snapshot_date": "2026-10-05",
        "revision": 1, "run_id": "20261005T141210Z-9c41e2",
        "manifest_path": "aws/manifests/2026-10-05/manifest.json",
        "updated_at": "2026-10-05T14:19:03Z",
    }).encode())
    selection = select_snapshot(S3Store("bucket", client=client), "aws", None, at_startup=True)
    assert selection.manifest is None
    assert "path" in selection.rejected.reason
    assert all(key.endswith(".json") for _, key in client.calls)


# --- previous_snapshot (icon coverage's "is this service new?") ------------------------------


def test_previous_snapshot_is_the_newest_succeeded_date_before_the_active_one(tmp_path):
    store = _root(tmp_path, [
        {"date": "2026-09-20"},
        {"date": "2026-09-27", "status": "partial", "failed_regions": [("us-east-1", "x")]},
        {"date": "2026-09-28", "status": "purged"},
        {"date": "2026-09-29", "status": "failed", "failed_regions": [("us-east-1", "x")]},
        {"date": "2026-10-05", "point_latest": True},
    ])
    previous = previous_snapshot(store, "aws", "2026-10-05")
    assert previous.snapshot_date == "2026-09-20"


def test_previous_snapshot_is_none_when_there_is_none(tmp_path):
    store = _root(tmp_path, [{"date": "2026-10-05", "point_latest": True}])
    assert previous_snapshot(store, "aws", "2026-10-05") is None
