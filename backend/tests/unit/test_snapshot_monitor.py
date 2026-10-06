"""The snapshot monitor (018-app-cloud-deployment, FR-012–FR-014; Story 5; data-model.md §5).
Constitution V: test-first.

`check_snapshots` is the testable core of each check: it chooses the manifest, switches the
active snapshot as a whole when a newer usable one appears, and otherwise keeps serving what it
has, recording why in the state the Admin tab shows.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.pricing_data.active_snapshot import MonitorState, check_snapshots
from src.pricing_data.manifest import Manifest
from src.pricing_data.snapshot import ActiveSnapshot
from src.pricing_data.snapshot_cache import CacheError
from src.pricing_data.storage import LocalStore
from tests.helpers.parquet_tree import make_pipeline_root


def _in_place(store: LocalStore):
    def materialize(manifest: Manifest, *, pinned: bool) -> ActiveSnapshot:
        return ActiveSnapshot.from_manifest(manifest, base_dir=store.root, pinned=pinned)

    return materialize


def _check(store, state, *, at_startup=False, pinned=None, materialize=None):
    return check_snapshots(
        store, "aws", state, pinned, at_startup=at_startup,
        materialize=materialize or _in_place(store),
    )


def _point(root, date_, revision=1):
    make_pipeline_root(root, [{"date": date_, "revision": revision, "point_latest": True}])


def test_startup_selects_the_pointer_and_needs_the_analysis(tmp_path):
    _point(tmp_path, "2026-10-05")
    state = MonitorState()
    result = _check(LocalStore(tmp_path), state, at_startup=True)
    assert state.active.snapshot_date == "2026-10-05"
    assert result.switched is True
    assert result.analysis_needed is True
    assert state.last_check_error is None


def test_a_newer_succeeded_date_switches_and_records_the_previous(tmp_path):
    _point(tmp_path, "2026-10-05")
    store, state = LocalStore(tmp_path), MonitorState()
    _check(store, state, at_startup=True)
    _point(tmp_path, "2026-10-12")
    result = _check(store, state)
    assert state.active.snapshot_date == "2026-10-12"
    assert result.switched is True
    assert result.previous.snapshot_date == "2026-10-05"
    assert result.analysis_needed is True


def test_a_newer_revision_of_the_same_date_switches(tmp_path):
    _point(tmp_path, "2026-10-05", revision=1)
    store, state = LocalStore(tmp_path), MonitorState()
    _check(store, state, at_startup=True)
    _point(tmp_path, "2026-10-05", revision=2)
    result = _check(store, state)
    assert (state.active.snapshot_date, state.active.revision) == ("2026-10-05", 2)
    assert result.switched is True


def test_no_change_means_no_switch_and_no_analysis(tmp_path):
    _point(tmp_path, "2026-10-05")
    store, state = LocalStore(tmp_path), MonitorState()
    _check(store, state, at_startup=True)
    result = _check(store, state)
    assert result.switched is False
    assert result.analysis_needed is False


def test_a_partial_newest_run_does_not_switch_and_is_shown(tmp_path):
    _point(tmp_path, "2026-10-05")
    store, state = LocalStore(tmp_path), MonitorState()
    _check(store, state, at_startup=True)
    make_pipeline_root(tmp_path, [{
        "date": "2026-10-12", "status": "partial", "regions": ["us-east-1", "ap-northeast-1"],
        "failed_regions": [("ap-northeast-1", "price list download timed out")],
    }])
    result = _check(store, state)
    assert result.switched is False
    assert state.active.snapshot_date == "2026-10-05"
    assert state.latest_run.snapshot_date == "2026-10-12"
    assert state.latest_run.status == "partial"
    assert [f.region for f in state.latest_run.failed_regions] == ["ap-northeast-1"]


def test_an_unreachable_source_keeps_the_active_snapshot(tmp_path):
    _point(tmp_path, "2026-10-05")
    store, state = LocalStore(tmp_path), MonitorState()
    _check(store, state, at_startup=True)

    class Down(LocalStore):
        def get(self, key):
            raise ConnectionError("could not connect to the endpoint")

    result = _check(Down(tmp_path), state)
    assert result.switched is False
    assert state.active.snapshot_date == "2026-10-05"
    assert "could not connect" in state.last_check_error


def test_a_failed_fetch_keeps_the_active_snapshot_and_is_retried(tmp_path):
    _point(tmp_path, "2026-10-05")
    store, state = LocalStore(tmp_path), MonitorState()
    _check(store, state, at_startup=True)
    _point(tmp_path, "2026-10-12")

    def failing(manifest, *, pinned):
        raise CacheError("aws/parquet/x.parquet: sha256 mismatch")

    result = _check(store, state, materialize=failing)
    assert result.switched is False
    assert state.active.snapshot_date == "2026-10-05"
    assert state.rejected.snapshot_date == "2026-10-12"
    assert "sha256" in state.rejected.reason

    result = _check(store, state)  # the next check tries again
    assert result.switched is True
    assert state.active.snapshot_date == "2026-10-12"
    assert state.rejected is None


def test_a_rejected_manifest_keeps_the_active_snapshot(tmp_path):
    _point(tmp_path, "2026-10-05")
    store, state = LocalStore(tmp_path), MonitorState()
    _check(store, state, at_startup=True)
    make_pipeline_root(tmp_path, [{"date": "2026-10-12", "point_latest": True,
                                   "schema_versions": {"product_dim": 7}}])
    result = _check(store, state)
    assert result.switched is False
    assert state.active.snapshot_date == "2026-10-05"
    assert "schema version 7" in state.rejected.reason


def test_no_snapshot_at_startup_is_not_an_error_but_is_reported(tmp_path):
    make_pipeline_root(tmp_path, [{"date": "2026-10-05"}])  # no pointer
    state = MonitorState()
    result = _check(LocalStore(tmp_path), state, at_startup=True)
    assert state.active is None
    assert result.analysis_needed is False
    assert state.last_check_error == "no snapshot available"


def test_regions_lost_in_a_switch_become_a_missing_regions_issue(tmp_path):
    make_pipeline_root(tmp_path, [{"date": "2026-10-05", "point_latest": True,
                                   "regions": ["us-east-1", "eu-west-1"]}])
    store, state = LocalStore(tmp_path), MonitorState()
    _check(store, state, at_startup=True)
    make_pipeline_root(tmp_path, [{"date": "2026-10-12", "point_latest": True,
                                   "regions": ["us-east-1"]}])
    _check(store, state)
    issues = [i for i in state.issues if i.kind == "missing_regions"]
    assert len(issues) == 1
    assert issues[0].regions == ["eu-west-1"]
    assert issues[0].snapshot_date == "2026-10-12"


def test_a_pin_never_moves(tmp_path):
    make_pipeline_root(
        tmp_path, [{"date": "2026-10-01"}, {"date": "2026-10-05", "point_latest": True}]
    )
    store, state = LocalStore(tmp_path), MonitorState()
    _check(store, state, at_startup=True, pinned=date(2026, 10, 1))
    _point(tmp_path, "2026-10-12")
    result = _check(store, state, pinned=date(2026, 10, 1))
    assert result.switched is False
    assert state.active.snapshot_date == "2026-10-01"
    assert state.active.pinned is True


def test_the_active_snapshot_never_moves_backwards(tmp_path):
    _point(tmp_path, "2026-10-12")
    store, state = LocalStore(tmp_path), MonitorState()
    _check(store, state, at_startup=True)
    _point(tmp_path, "2026-10-05")  # a stale pointer
    result = _check(store, state)
    assert result.switched is False
    assert state.active.snapshot_date == "2026-10-12"


@pytest.mark.parametrize("at_startup", [True, False])
def test_check_time_is_recorded(tmp_path, at_startup):
    _point(tmp_path, "2026-10-05")
    state = MonitorState()
    _check(LocalStore(tmp_path), state, at_startup=at_startup)
    assert state.last_check_at is not None
    assert state.initialized is True
