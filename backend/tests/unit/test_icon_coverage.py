"""Icon coverage analysis (016-canvas-icon-layout, US5: FR-022–FR-024, data-model.md §2–3):
which services in the active snapshot have no icon, and which of those are new.

018-app-cloud-deployment: services come from the files the manifests list, and the snapshot a
service is "new" against is the newest usable manifest before the active one."""

from __future__ import annotations

from src.pricing_data.active_snapshot import MonitorState
from src.pricing_data.icon_coverage import analyze, find_unmatched_services
from src.pricing_data.manifest import Manifest
from src.pricing_data.snapshot import ActiveSnapshot
from src.pricing_data.storage import LocalStore
from tests.helpers.parquet_tree import make_pipeline_root

OLD, NEW = "2026-09-23", "2026-09-24"


def _snapshot(root, date_: str) -> ActiveSnapshot:
    manifest = Manifest.model_validate_json(
        (root / f"aws/manifests/{date_}/manifest.json").read_text()
    )
    return ActiveSnapshot.from_manifest(manifest, base_dir=root, pinned=False)


def _tree(tmp_path):
    return make_pipeline_root(
        tmp_path,
        [
            {"date": OLD, "services": [("ZZOldService", "Old Service"),
                                       ("AmazonDynamoDB", "DynamoDB")]},
            {
                "date": NEW,
                "point_latest": True,
                "services": [
                    ("AmazonDynamoDB", "Amazon DynamoDB"),
                    ("AWSDataTransfer", "AWS Data Transfer"),
                    ("ZZNewService", "New Service"),
                    ("ZZOldService", "Old Service"),
                ],
            },
        ],
    )


def _unmatched(tmp_path, with_previous=True):
    root = _tree(tmp_path)
    previous = _snapshot(root, OLD) if with_previous else None
    return find_unmatched_services(_snapshot(root, NEW), previous)


def test_lists_only_services_without_an_icon(tmp_path):
    issues = _unmatched(tmp_path)
    assert [i.service_code for i in issues] == ["ZZNewService", "ZZOldService"]
    assert all(i.kind == "missing_icon" and i.snapshot_date == NEW for i in issues)


def test_marks_services_absent_from_the_previous_snapshot_as_new(tmp_path):
    by_code = {i.service_code: i for i in _unmatched(tmp_path)}
    assert by_code["ZZNewService"].is_new is True
    assert by_code["ZZOldService"].is_new is False


def test_takes_service_names_from_service_dim(tmp_path):
    by_code = {i.service_code: i for i in _unmatched(tmp_path)}
    assert by_code["ZZNewService"].service_name == "New Service"
    assert "ZZNewService" in by_code["ZZNewService"].message


def test_nothing_is_new_without_a_previous_snapshot(tmp_path):
    issues = _unmatched(tmp_path, with_previous=False)
    assert {i.is_new for i in issues} == {False}


def test_analysis_flags_new_services_against_the_previous_usable_manifest(tmp_path):
    root = _tree(tmp_path)
    state = MonitorState(active=_snapshot(root, NEW))
    analyze(state, LocalStore(root), None)
    by_code = {i.service_code: i for i in state.issues}
    assert by_code["ZZNewService"].is_new is True
    assert by_code["ZZOldService"].is_new is False


# --- 017-structured-json-logging, FR-008 d: coverage log events -----------------------------


def test_analysis_logs_a_summary_and_one_debug_line_per_service(tmp_path, log_output):
    root = _tree(tmp_path)
    state = MonitorState(active=_snapshot(root, NEW))
    analyze(state, LocalStore(root), None)

    missing = [i for i in state.issues if i.kind == "missing_icon"]
    records = log_output()
    [summary] = [r for r in records if r["message"] == "icon coverage analyzed"]
    assert summary["level"] == "info"
    assert summary["snapshot_date"] == NEW
    assert summary["missing_icon_count"] == len(missing) == 2
    assert summary["new_service_codes"] == sorted(i.service_code for i in missing if i.is_new)
    assert summary["new_service_codes"] == ["ZZNewService"]

    per_service = [r for r in records if r["message"] == "service has no icon"]
    assert all(r["level"] == "debug" for r in per_service)
    assert [
        (r["snapshot_date"], r["service_code"], r["service_name"], r["is_new"]) for r in per_service
    ] == [(NEW, i.service_code, i.service_name, i.is_new) for i in missing]


def test_full_coverage_logs_zero_and_no_debug_lines(tmp_path, log_output):
    make_pipeline_root(
        tmp_path, [{"date": NEW, "services": [("AmazonDynamoDB", "Amazon DynamoDB")]}]
    )
    analyze(MonitorState(active=_snapshot(tmp_path, NEW)), LocalStore(tmp_path), None)

    records = log_output()
    [summary] = [r for r in records if r["message"] == "icon coverage analyzed"]
    assert summary["missing_icon_count"] == 0
    assert summary["new_service_codes"] == []
    assert not [r for r in records if r["message"] == "service has no icon"]
