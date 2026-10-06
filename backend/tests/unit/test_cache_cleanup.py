"""Cache clean-up policy (018-app-cloud-deployment, FR-011, SC-006; data-model.md §4).
Constitution V: test-first.

`plan_cleanup` is pure. The active snapshot is never deleted; a snapshot is never deleted by
the check that superseded it (a request may still be reading it); after that, anything beyond
the keep count, over the size limit, or purged by the pipeline goes.
"""

from __future__ import annotations

from pathlib import Path

from src.pricing_data.snapshot_cache import CacheEntry, plan_cleanup

GB = 10**9


def _entry(date: str, revision: int = 1, size: int = GB) -> CacheEntry:
    return CacheEntry(Path(f"/cache/aws/{date}-r{revision}"), date, revision, size,
                      "2026-10-01T00:00:00Z")


def _names(paths) -> list[str]:
    return [p.name for p in paths]


def test_the_active_entry_is_never_deleted():
    active = _entry("2026-10-05")
    assert plan_cleanup([active], active=active, keep=0, max_bytes=1,
                        superseded_this_check=None, purged_dates=set()) == []


def test_the_entry_superseded_by_this_check_survives_until_the_next():
    old, active = _entry("2026-10-05"), _entry("2026-10-12")
    kwargs = dict(active=active, keep=0, max_bytes=10 * GB, purged_dates=set())
    assert plan_cleanup([old, active], superseded_this_check=old, **kwargs) == []
    assert _names(plan_cleanup([old, active], superseded_this_check=None, **kwargs)) == [
        "2026-10-05-r1"
    ]


def test_entries_within_keep_are_kept_and_the_rest_go_oldest_first():
    entries = [_entry(d) for d in ("2026-09-21", "2026-09-28", "2026-10-05")]
    active = _entry("2026-10-12")
    deletions = plan_cleanup(entries + [active], active=active, keep=1, max_bytes=100 * GB,
                             superseded_this_check=None, purged_dates=set())
    assert _names(deletions) == ["2026-09-21-r1", "2026-09-28-r1"]


def test_the_size_limit_is_enforced_oldest_first():
    entries = [_entry("2026-09-28", size=3 * GB), _entry("2026-10-05", size=3 * GB)]
    active = _entry("2026-10-12", size=3 * GB)
    deletions = plan_cleanup(entries + [active], active=active, keep=5, max_bytes=7 * GB,
                             superseded_this_check=None, purged_dates=set())
    assert _names(deletions) == ["2026-09-28-r1"]


def test_purged_entries_are_deleted_even_within_keep():
    purged, active = _entry("2026-10-05"), _entry("2026-10-12")
    deletions = plan_cleanup([purged, active], active=active, keep=5, max_bytes=100 * GB,
                             superseded_this_check=None, purged_dates={"2026-10-05"})
    assert _names(deletions) == ["2026-10-05-r1"]


def test_an_older_revision_of_the_active_date_counts_like_any_other_entry():
    rev1, active = _entry("2026-10-12", 1), _entry("2026-10-12", 2)
    deletions = plan_cleanup([rev1, active], active=active, keep=0, max_bytes=100 * GB,
                             superseded_this_check=None, purged_dates=set())
    assert _names(deletions) == ["2026-10-12-r1"]


def test_with_no_active_snapshot_nothing_is_protected_but_keep_still_applies():
    entries = [_entry("2026-10-05"), _entry("2026-10-12")]
    deletions = plan_cleanup(entries, active=None, keep=1, max_bytes=100 * GB,
                             superseded_this_check=None, purged_dates=set())
    assert _names(deletions) == ["2026-10-05-r1"]


# --- Wired into the monitor (S3 source) -----------------------------------------------------


def test_run_check_cleans_the_cache_one_check_after_a_switch(tmp_path, monkeypatch):
    from src.pricing_data import active_snapshot
    from src.pricing_data.storage import S3Store
    from tests.helpers.fake_s3 import FakeS3Client
    from tests.helpers.parquet_tree import make_pipeline_root

    client = FakeS3Client()

    def publish(date: str) -> None:
        root = make_pipeline_root(tmp_path / f"src-{date}", [{"date": date, "point_latest": True}])
        for path in root.rglob("*"):
            if path.is_file():
                client.put("bucket", str(path.relative_to(root)), path.read_bytes())

    cache = tmp_path / "cache"
    monkeypatch.setattr(active_snapshot.settings, "pricing_cache_dir", str(cache))
    monkeypatch.setattr(active_snapshot.settings, "pricing_cache_keep", 0)
    monkeypatch.setattr(active_snapshot.settings, "active_snapshot_date", None)
    monkeypatch.setattr(active_snapshot, "open_store", lambda _s: S3Store("bucket", client=client))
    monkeypatch.setattr(active_snapshot, "STATE", active_snapshot.MonitorState())
    active_snapshot.set_analysis_hook(lambda *a: None)
    try:
        publish("2026-10-05")
        active_snapshot.run_check(at_startup=True)
        assert [e.path.name for e in active_snapshot.STATE.cache] == ["2026-10-05-r1"]

        publish("2026-10-12")
        assert active_snapshot.run_check().switched
        # Superseded by this very check: kept, a request may still be reading it.
        assert [e.path.name for e in active_snapshot.STATE.cache] == [
            "2026-10-05-r1", "2026-10-12-r1"
        ]

        active_snapshot.run_check()
        assert [e.path.name for e in active_snapshot.STATE.cache] == ["2026-10-12-r1"]
        assert not (cache / "aws" / "2026-10-05-r1").exists()
    finally:
        active_snapshot.set_analysis_hook(None)
