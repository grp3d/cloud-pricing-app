"""The price history backfill (019, T069, research R10) on the T007 fixture, from a local root
and from an S3-style source."""

from __future__ import annotations

import json
import shutil

import pytest

from src.config import settings
from src.pricing_data.history import builder, service
from src.pricing_data.history.service import history_store, update_history
from src.pricing_data.storage import LocalStore, S3Store
from tests.helpers.fake_s3 import FakeS3Client
from tests.helpers.history import TRENDS_ROOT

WEEKS = ["2026-09-07 r1", "2026-09-14 r1", "2026-09-21 r2", "2026-10-05 r1", "2026-10-12 r1"]


@pytest.fixture(autouse=True)
def history_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "pricing_history_dir", str(tmp_path / "history"))
    monkeypatch.setattr(settings, "pricing_cache_dir", str(tmp_path / "cache"))
    return tmp_path / "history"


def _bucket() -> tuple[FakeS3Client, S3Store]:
    client = FakeS3Client()
    for path in TRENDS_ROOT.rglob("*"):
        if path.is_file() and "/aws/" in f"/{path.relative_to(TRENDS_ROOT)}":
            client.put("bucket", str(path.relative_to(TRENDS_ROOT)), path.read_bytes())
    return client, S3Store("bucket", client=client)


def _opened_in_order(monkeypatch) -> list[str]:
    opened: list[str] = []
    real = builder.build_history

    def spy(store, weeks, write_prices, open_snapshot, **kwargs):
        def counting(week):
            opened.append(week.label)
            return open_snapshot(week)

        return real(store, weeks, write_prices, counting, **kwargs)

    monkeypatch.setattr(service, "build_history", spy)
    return opened


def test_a_backfill_walks_oldest_to_newest_and_records_its_state(monkeypatch):
    opened = _opened_in_order(monkeypatch)
    assert update_history("aws", source=LocalStore(TRENDS_ROOT)) is True
    assert opened == WEEKS
    state = history_store("aws").state()
    assert (state["backfill"], state["weeks_built"], state["weeks_total"]) == ("done", 4, 4)
    assert state["gaps"] == ["2026-09-28"] and state["last_error"] is None
    assert state["weeks"] == WEEKS


def test_a_restart_after_it_finishes_fetches_nothing(monkeypatch):
    update_history("aws", source=LocalStore(TRENDS_ROOT))
    opened = _opened_in_order(monkeypatch)
    update_history("aws", source=LocalStore(TRENDS_ROOT))
    assert opened == []


def test_an_interrupted_backfill_resumes(monkeypatch):
    real = builder.build_pair
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real(*args, **kwargs)

    monkeypatch.setattr(builder, "build_pair", flaky)
    update_history("aws", source=LocalStore(TRENDS_ROOT))
    state = history_store("aws").state()
    assert (state["backfill"], state["weeks_built"]) == ("failed", 1)
    assert "disk full" in state["last_error"]

    monkeypatch.setattr(builder, "build_pair", real)
    opened = _opened_in_order(monkeypatch)
    update_history("aws", source=LocalStore(TRENDS_ROOT))
    assert history_store("aws").state()["backfill"] == "done"
    assert "2026-09-07 r1" not in opened  # the finished first pair isn't redone


def test_an_s3_source_fetches_only_the_comparable_tables_and_deletes_them(tmp_path):
    client, store = _bucket()
    downloads: list[str] = []
    client.before_call = lambda op, key: downloads.append(key) if op == "GetObject" else None
    update_history("aws", source=store)
    parquet = [k for k in downloads if k.endswith(".parquet")]
    tables = {k.split("/")[2] for k in parquet}
    assert tables == {"price_fact", "product_dim", "service_dim"}
    # Each historical snapshot's files are fetched once, verified, and the copy is gone.
    assert len(parquet) == len(set(parquet))
    assert not any(p.name.startswith("history-") for p in (tmp_path / "cache").iterdir())
    state = history_store("aws").state()
    assert (state["backfill"], state["weeks_built"]) == ("done", 4)


def test_an_s3_file_that_fails_verification_records_the_error(tmp_path):
    client, store = _bucket()
    key = next(k for k in client.keys("bucket") if "/price_fact/" in k)
    client.put("bucket", key, b"tampered")
    update_history("aws", source=store)
    state = history_store("aws").state()
    assert state["backfill"] == "failed" and "sha256" in state["last_error"]


def test_a_corrupt_file_triggers_a_rebuild_of_that_pair(history_dir):
    update_history("aws", source=LocalStore(TRENDS_ROOT))
    pair = history_dir / "aws" / "pairs" / "2026-09-14_2026-09-21"
    (pair / "changes.parquet").write_bytes(b"\x00garbage")
    update_history("aws", source=LocalStore(TRENDS_ROOT))
    meta = json.loads((pair / "pair.json").read_text())
    assert meta["to_snapshot"] == "2026-09-21 r2"
    import duckdb

    assert duckdb.sql(f"SELECT count(*) FROM '{pair / 'changes.parquet'}'").fetchone()[0] == 2


def test_a_new_snapshot_adds_its_week(tmp_path):
    root = tmp_path / "root"
    shutil.copytree(TRENDS_ROOT, root)
    newest = root / "aws" / "manifests" / "2026-10-12"
    newest.rename(root / "aws" / "manifests" / "hidden")
    update_history("aws", source=LocalStore(root))
    assert history_store("aws").state()["weeks_built"] == 3
    (root / "aws" / "manifests" / "hidden").rename(newest)
    update_history("aws", source=LocalStore(root))
    assert history_store("aws").state()["weeks_built"] == 4


def test_a_provider_build_already_running_is_not_started_twice():
    lock = service._locks["aws"]
    lock.acquire()
    try:
        assert update_history("aws", source=LocalStore(TRENDS_ROOT)) is False
    finally:
        lock.release()


def test_switch_hook_starts_an_update(monkeypatch):
    from src.pricing_data import active_snapshot

    started: list[str] = []
    active_snapshot.set_switch_hook(started.append)
    try:
        active_snapshot.reset()
        active_snapshot.run_check(at_startup=True)
    finally:
        active_snapshot.set_switch_hook(None)
    assert set(started) == {"aws", "azure", "gcp"}
