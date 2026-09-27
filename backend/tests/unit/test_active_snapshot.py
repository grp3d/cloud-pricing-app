"""Active pricing snapshot selection (016-canvas-icon-layout, US4: FR-014–FR-019, data-model.md
§1–2, research.md §1–3). Runs against fake pricing-data trees (`tests/helpers/parquet_tree.py`):
only folder layout and `_SUCCESS` markers matter to the monitor."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from src.pricing_data import active_snapshot
from src.pricing_data.active_snapshot import (
    ActiveSnapshotConfigError,
    ActiveSnapshotState,
    check_snapshots,
)
from src.pricing_data.errors import PricingDataUnavailableError
from tests.helpers.parquet_tree import make_snapshot_tree

D1, D2, D3 = "2026-09-23", "2026-09-24", "2026-09-25"


def _check(root: Path, state: ActiveSnapshotState, override=None, *, at_startup=False):
    return check_snapshots(root, state, override, at_startup=at_startup)


# --- (a) newest complete date --------------------------------------------------------------


def test_picks_newest_date_with_markers_in_every_table(tmp_path):
    make_snapshot_tree(tmp_path, {D1: {}, D2: {}})
    state = ActiveSnapshotState()
    _check(tmp_path, state, at_startup=True)
    assert state.active_date == D2
    assert not state.pinned


# --- (b) incomplete dates wait ------------------------------------------------------------


def test_newer_date_missing_a_table_waits(tmp_path):
    make_snapshot_tree(tmp_path, {D1: {}, D2: {"tables_missing": ["price_fact"]}})
    state = ActiveSnapshotState()
    _check(tmp_path, state, at_startup=True)
    assert state.active_date == D1
    assert [(w.snapshot_date, w.reason) for w in state.waiting] == [
        (D2, "missing from price_fact")
    ]


def test_newer_date_missing_a_marker_waits(tmp_path):
    make_snapshot_tree(tmp_path, {D1: {}, D2: {"markers_missing": ["product_dim"]}})
    state = ActiveSnapshotState()
    _check(tmp_path, state, at_startup=True)
    assert state.active_date == D1
    assert [(w.snapshot_date, w.reason) for w in state.waiting] == [
        (D2, "no completion marker in product_dim")
    ]


def test_waiting_date_becomes_active_once_complete(tmp_path):
    make_snapshot_tree(tmp_path, {D1: {}, D2: {"markers_missing": ["product_dim"]}})
    state = ActiveSnapshotState()
    _check(tmp_path, state, at_startup=True)
    (tmp_path / "product_dim" / f"snapshot_date={D2}" / "_SUCCESS").touch()
    result = _check(tmp_path, state)
    assert state.active_date == D2
    assert result.switched
    assert state.waiting == []


# --- (c) missing regions on a running switch only -----------------------------------------


def test_running_switch_records_missing_regions(tmp_path):
    make_snapshot_tree(tmp_path, {D1: {"regions": ["eu-west-1", "us-east-1"]}})
    state = ActiveSnapshotState()
    _check(tmp_path, state, at_startup=True)
    make_snapshot_tree(tmp_path, {D2: {"regions": ["us-east-1"]}})
    _check(tmp_path, state)
    assert state.active_date == D2
    region_issues = [i for i in state.issues if i.kind == "missing_regions"]
    assert len(region_issues) == 1
    assert region_issues[0].regions == ["eu-west-1"]
    assert region_issues[0].snapshot_date == D2


def test_startup_does_not_record_missing_regions(tmp_path):
    make_snapshot_tree(
        tmp_path, {D1: {"regions": ["eu-west-1", "us-east-1"]}, D2: {"regions": ["us-east-1"]}}
    )
    state = ActiveSnapshotState()
    _check(tmp_path, state, at_startup=True)
    assert state.active_date == D2
    assert [i for i in state.issues if i.kind == "missing_regions"] == []


# --- (d) override -------------------------------------------------------------------------


def test_override_on_date_without_markers_is_pinned_with_warning(tmp_path):
    make_snapshot_tree(tmp_path, {D1: {"markers": False}, D2: {}})
    state = ActiveSnapshotState()
    _check(tmp_path, state, date.fromisoformat(D1), at_startup=True)
    assert state.active_date == D1
    assert state.pinned
    kinds = [i.kind for i in state.issues]
    assert kinds.count("pinned_incomplete") == 1


def test_override_on_date_missing_from_a_table_refuses_to_start(tmp_path):
    make_snapshot_tree(tmp_path, {D1: {"tables_missing": ["region_dim"]}, D2: {}})
    with pytest.raises(ActiveSnapshotConfigError, match="ACTIVE_SNAPSHOT_DATE"):
        _check(tmp_path, ActiveSnapshotState(), date.fromisoformat(D1), at_startup=True)


# --- (e) pinned date never moves ----------------------------------------------------------


def test_pinned_date_ignores_newer_complete_snapshot(tmp_path):
    make_snapshot_tree(tmp_path, {D1: {}})
    state = ActiveSnapshotState()
    _check(tmp_path, state, date.fromisoformat(D1), at_startup=True)
    make_snapshot_tree(tmp_path, {D2: {}})
    result = _check(tmp_path, state, date.fromisoformat(D1))
    assert state.active_date == D1
    assert not result.switched
    assert state.waiting == []


# --- (f) nothing complete -----------------------------------------------------------------


def test_no_complete_date_leaves_no_active_date_with_reason(tmp_path):
    make_snapshot_tree(tmp_path, {D1: {"markers": False}})
    state = ActiveSnapshotState()
    _check(tmp_path, state, at_startup=True)
    assert state.active_date is None
    assert state.last_check_error


# --- (g) when the icon analysis runs ------------------------------------------------------


def test_analysis_needed_at_startup_switch_and_marker_change_only(tmp_path):
    make_snapshot_tree(tmp_path, {D1: {}})
    state = ActiveSnapshotState()
    assert _check(tmp_path, state, at_startup=True).analysis_needed

    assert not _check(tmp_path, state).analysis_needed

    marker = tmp_path / "service_dim" / f"snapshot_date={D1}" / "_SUCCESS"
    stat = marker.stat()
    os.utime(marker, (stat.st_atime + 60, stat.st_mtime + 60))
    assert _check(tmp_path, state).analysis_needed

    make_snapshot_tree(tmp_path, {D2: {}})
    assert _check(tmp_path, state).analysis_needed
    assert not _check(tmp_path, state).analysis_needed


# --- (h) unreadable data ------------------------------------------------------------------


def test_unreadable_data_keeps_active_date_and_records_error(tmp_path):
    make_snapshot_tree(tmp_path, {D1: {}})
    state = ActiveSnapshotState()
    _check(tmp_path, state, at_startup=True)
    result = _check(tmp_path / "does-not-exist", state)
    assert state.active_date == D1
    assert state.last_check_error
    assert not result.analysis_needed


# --- (i) last check time ------------------------------------------------------------------


def test_every_check_records_its_time(tmp_path):
    make_snapshot_tree(tmp_path, {D1: {}})
    state = ActiveSnapshotState()
    _check(tmp_path, state, at_startup=True)
    first = state.last_check_at
    _check(tmp_path, state)
    assert first is not None
    assert state.last_check_at >= first


# --- get_active_snapshot_date (T012) ------------------------------------------------------


@pytest.fixture
def fresh_state(monkeypatch, tmp_path):
    monkeypatch.setattr(active_snapshot, "STATE", ActiveSnapshotState())
    monkeypatch.setattr(active_snapshot.settings, "aws_pricing_parquet_dir", str(tmp_path))
    monkeypatch.setattr(active_snapshot.settings, "active_snapshot_date", None)
    return tmp_path


def test_get_active_snapshot_date_initializes_lazily(fresh_state):
    make_snapshot_tree(fresh_state, {D1: {}, D3: {}})
    assert active_snapshot.get_active_snapshot_date() == D3
    assert active_snapshot.STATE.initialized


def test_get_active_snapshot_date_returns_state_without_rescanning(fresh_state):
    make_snapshot_tree(fresh_state, {D1: {}})
    assert active_snapshot.get_active_snapshot_date() == D1
    make_snapshot_tree(fresh_state, {D2: {}})  # not picked up until the next check
    assert active_snapshot.get_active_snapshot_date() == D1


def test_get_active_snapshot_date_raises_when_none(fresh_state):
    make_snapshot_tree(fresh_state, {D1: {"markers": False}})
    with pytest.raises(PricingDataUnavailableError):
        active_snapshot.get_active_snapshot_date()


# --- FR-019: one snapshot date per request (T016) -------------------------------------------


def test_architecture_detail_uses_one_snapshot_date_throughout(monkeypatch):
    """Even if the active date changes mid-request, every lookup in one architecture response
    uses the date read at the start — never a mix of two days' data."""
    import uuid
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from src.models.schemas import ArchitectureDetailOut
    from src.services import architecture_service

    dates = iter(["2026-09-24", "2026-09-25", "2026-09-25", "2026-09-25", "2026-09-25"])
    monkeypatch.setattr(architecture_service, "get_active_snapshot_date", lambda: next(dates))

    seen: list[str] = []

    def fake_units(keys, *, region, snapshot_date=None):
        seen.append(snapshot_date)
        return {}

    def fake_details(skus, *, region, snapshot_date=None):
        seen.append(snapshot_date)
        return {}

    monkeypatch.setattr(architecture_service, "resolve_units", fake_units)
    monkeypatch.setattr(architecture_service, "resolve_product_details", fake_details)

    def selection():
        return SimpleNamespace(
            id=uuid.uuid4(),
            service_code="AmazonEC2",
            sku="SKU",
            pricing_term="on_demand",
            purchase_option="not_applicable",
            usage_quantity=1,
        )

    collections = [
        SimpleNamespace(
            id=uuid.uuid4(),
            type="application_component",
            name=f"box-{region}",
            region=region,
            parent_collection_id=None,
            deleted_at=None,
            sku_selections=[selection()],
        )
        for region in ("us-east-1", "eu-west-1")
    ]
    architecture = SimpleNamespace(
        id=uuid.uuid4(),
        name="A",
        provider="aws",
        created_at=datetime.now(UTC),
        is_public=False,
        collections=collections,
        connectors=[],
    )
    detail = ArchitectureDetailOut.model_validate(architecture)

    architecture_service.attach_units_to_architecture(detail, architecture)

    assert len(seen) == 4  # units + details, per region
    assert set(seen) == {"2026-09-24"}
