"""Icon coverage analysis (016-canvas-icon-layout, US5: FR-022–FR-024, data-model.md §2–3):
which services in the active snapshot have no icon, and which of those are new."""

from __future__ import annotations

from src.pricing_data.active_snapshot import ActiveSnapshotState
from src.pricing_data.icon_coverage import (
    analyze,
    find_unmatched_services,
    previous_present_date,
)
from tests.helpers.parquet_tree import make_snapshot_tree

OLD, NEW = "2026-09-23", "2026-09-24"


def _tree(tmp_path):
    return make_snapshot_tree(
        tmp_path,
        {
            OLD: {"services": [("ZZOldService", "Old Service"), ("AmazonDynamoDB", "DynamoDB")]},
            NEW: {
                "services": [
                    ("AmazonDynamoDB", "Amazon DynamoDB"),
                    ("AWSDataTransfer", "AWS Data Transfer"),
                    ("ZZNewService", "New Service"),
                    ("ZZOldService", "Old Service"),
                ]
            },
        },
    )


def test_lists_only_services_without_an_icon(tmp_path):
    issues = find_unmatched_services(_tree(tmp_path), NEW, OLD)
    assert [i.service_code for i in issues] == ["ZZNewService", "ZZOldService"]
    assert all(i.kind == "missing_icon" and i.snapshot_date == NEW for i in issues)


def test_marks_services_absent_from_the_previous_snapshot_as_new(tmp_path):
    by_code = {i.service_code: i for i in find_unmatched_services(_tree(tmp_path), NEW, OLD)}
    assert by_code["ZZNewService"].is_new is True
    assert by_code["ZZOldService"].is_new is False


def test_takes_service_names_from_service_dim(tmp_path):
    by_code = {i.service_code: i for i in find_unmatched_services(_tree(tmp_path), NEW, OLD)}
    assert by_code["ZZNewService"].service_name == "New Service"
    assert "ZZNewService" in by_code["ZZNewService"].message


def test_nothing_is_new_without_a_previous_snapshot(tmp_path):
    issues = find_unmatched_services(_tree(tmp_path), NEW, None)
    assert {i.is_new for i in issues} == {False}


def test_previous_present_date_ignores_markers_and_requires_every_table(tmp_path):
    make_snapshot_tree(
        tmp_path,
        {
            "2026-09-20": {"markers": False},
            "2026-09-21": {"tables_missing": ["price_fact"]},
            NEW: {},
        },
    )
    assert previous_present_date(tmp_path, NEW) == "2026-09-20"
    assert previous_present_date(tmp_path, "2026-09-20") is None


# --- 017-structured-json-logging, FR-008 d: coverage log events -----------------------------


def test_analysis_logs_a_summary_and_one_debug_line_per_service(tmp_path, log_output):
    state = ActiveSnapshotState(active_date=NEW)
    analyze(state, _tree(tmp_path), None)

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
    make_snapshot_tree(tmp_path, {NEW: {"services": [("AmazonDynamoDB", "Amazon DynamoDB")]}})
    analyze(ActiveSnapshotState(active_date=NEW), tmp_path, None)

    records = log_output()
    [summary] = [r for r in records if r["message"] == "icon coverage analyzed"]
    assert summary["missing_icon_count"] == 0
    assert summary["new_service_codes"] == []
    assert not [r for r in records if r["message"] == "service has no icon"]
