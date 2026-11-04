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
    kwargs = {"active": active, "keep": 0, "max_bytes": 10 * GB, "purged_dates": set()}
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


# --- 019-gcp-azure-providers-trends (research R2): clean-up across providers ----------------


def _pentry(provider: str, date: str, revision: int = 1, size: int = GB) -> CacheEntry:
    return CacheEntry(Path(f"/cache/{provider}/{date}-r{revision}"), date, revision, size,
                      "2026-10-01T00:00:00Z")


def _view(entries, active, superseded=None, purged=()):
    from src.pricing_data.snapshot_cache import ProviderCache

    return ProviderCache(entries=entries, active=active, superseded_this_check=superseded,
                         purged_dates=set(purged))


def _paths(paths) -> list[str]:
    return sorted(f"{p.parent.name}/{p.name}" for p in paths)


def test_every_providers_active_entry_is_protected():
    from src.pricing_data.snapshot_cache import plan_cleanup_providers

    aws, azure = _pentry("aws", "2026-10-05", size=5 * GB), _pentry("azure", "2026-11-02")
    views = {"aws": _view([aws], aws), "azure": _view([azure], azure)}
    assert plan_cleanup_providers(views, keep=0, max_bytes=1) == []


def test_keep_applies_per_provider():
    from src.pricing_data.snapshot_cache import plan_cleanup_providers

    aws = [_pentry("aws", d) for d in ("2026-09-21", "2026-09-28", "2026-10-05")]
    azure = [_pentry("azure", d) for d in ("2026-10-19", "2026-10-26", "2026-11-02")]
    views = {"aws": _view(aws, aws[-1]), "azure": _view(azure, azure[-1])}
    deletions = plan_cleanup_providers(views, keep=1, max_bytes=100 * GB)
    assert _paths(deletions) == ["aws/2026-09-21-r1", "azure/2026-10-19-r1"]


def test_the_size_budget_is_shared_and_oldest_goes_first():
    from src.pricing_data.snapshot_cache import plan_cleanup_providers

    aws_old, aws_active = (_pentry("aws", "2026-10-05", size=3 * GB),
                           _pentry("aws", "2026-10-12", size=3 * GB))
    azure_old, azure_active = (_pentry("azure", "2026-10-26", size=GB),
                               _pentry("azure", "2026-11-02", size=GB))
    views = {
        "aws": _view([aws_old, aws_active], aws_active),
        "azure": _view([azure_old, azure_active], azure_active),
    }
    # 8 GB in all, budget 6 GB: the oldest unprotected entry (AWS 2026-10-05) goes.
    assert _paths(plan_cleanup_providers(views, keep=5, max_bytes=6 * GB)) == [
        "aws/2026-10-05-r1"
    ]
    # Budget 4 GB: both old entries go; the active ones stay even over budget.
    assert _paths(plan_cleanup_providers(views, keep=5, max_bytes=4 * GB)) == [
        "aws/2026-10-05-r1", "azure/2026-10-26-r1"
    ]


def test_superseded_and_purged_rules_apply_per_provider():
    from src.pricing_data.snapshot_cache import plan_cleanup_providers

    gcp_old, gcp_active = _pentry("gcp", "2026-10-26"), _pentry("gcp", "2026-11-02")
    azure_purged, azure_active = _pentry("azure", "2026-10-26"), _pentry("azure", "2026-11-02")
    views = {
        "gcp": _view([gcp_old, gcp_active], gcp_active, superseded=gcp_old),
        "azure": _view([azure_purged, azure_active], azure_active, purged={"2026-10-26"}),
    }
    assert _paths(plan_cleanup_providers(views, keep=0, max_bytes=100 * GB)) == [
        "azure/2026-10-26-r1"
    ]
