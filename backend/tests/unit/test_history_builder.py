"""The price history builder against the T007 Trends fixture (019, T066, data-model §7).
Expected numbers are the fixture README's."""

from __future__ import annotations

import json
import shutil
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from src.pricing_data.history import builder
from src.pricing_data.history.builder import build_history, select_weeks
from src.pricing_data.history.source import list_manifests, snapshot_opener
from src.pricing_data.history.store import HistoryStore
from src.pricing_data.providers.registry import get_provider
from src.pricing_data.storage import LocalStore

TRENDS = Path(__file__).resolve().parents[1] / "fixtures" / "trends"
aws = get_provider("aws")


class Run:
    """One build of a pipeline root into a history directory, counting snapshot opens."""

    def __init__(self, root: Path, history: Path) -> None:
        self.store = HistoryStore(history, "aws")
        self.source = LocalStore(root)
        self.opened: list[str] = []

    def __call__(self):
        weeks = select_weeks(list_manifests(self.source, "aws"))
        opener = snapshot_opener(self.source, aws.comparable_tables)

        @contextmanager
        def counting(week):
            self.opened.append(week.label)
            with opener(week) as snapshot:
                yield snapshot

        return build_history(self.store, weeks, aws.write_comparable_prices, counting)


def _counts(store: HistoryStore, pair: str) -> dict[str, tuple]:
    rows = duckdb.sql(
        "SELECT location, sum(compared), sum(unchanged), sum(increased), sum(decreased), "
        "sum(added), sum(removed), sum(excluded) FROM read_parquet(?) GROUP BY location",
        params=[str(store.pairs_dir / pair / "counts.parquet")],
    ).fetchall()
    return {r[0]: tuple(int(x) for x in r[1:]) for r in rows}


def _changes(store: HistoryStore, pair: str) -> set[tuple]:
    rows = duckdb.sql(
        "SELECT item_key, old_price, new_price FROM read_parquet(?)",
        params=[str(store.pairs_dir / pair / "changes.parquet")],
    ).fetchall()
    return {(r[0], Decimal(r[1]).normalize(), Decimal(r[2]).normalize()) for r in rows}


@pytest.fixture
def run(tmp_path):
    return Run(TRENDS, tmp_path / "history")


@pytest.fixture
def root_copy(tmp_path):
    root = tmp_path / "root"
    shutil.copytree(TRENDS, root)
    return root


PAIRS = ["2026-09-07_2026-09-14", "2026-09-14_2026-09-21", "2026-09-21_2026-10-05",
         "2026-10-05_2026-10-12"]
# compared, unchanged, increased, decreased, added, removed, excluded (README)
EXPECTED = {
    PAIRS[0]: {"us-east-1": (8, 7, 0, 1, 0, 0, 1), "us-west-2": (2, 2, 0, 0, 0, 0, 0)},
    PAIRS[1]: {"us-east-1": (8, 6, 2, 0, 1, 0, 1), "us-west-2": (2, 2, 0, 0, 0, 0, 0)},
    PAIRS[2]: {"us-east-1": (8, 7, 0, 1, 0, 1, 1), "us-west-2": (2, 2, 0, 0, 0, 0, 0)},
    PAIRS[3]: {"us-east-1": (8, 7, 0, 1, 0, 0, 1), "us-west-2": (2, 1, 1, 0, 0, 0, 0)},
}


def test_counts_per_week_pair_match_the_readme(run):
    result = run()
    assert result.weeks_total == 4 and sorted(result.built) == PAIRS
    for pair, expected in EXPECTED.items():
        assert _counts(run.store, pair) == expected, pair


def test_changes_hold_exactly_the_changed_items(run):
    run()
    d = Decimal
    assert _changes(run.store, PAIRS[0]) == {("TRDFALL000000001", d("0.2"), d("0.18"))}
    assert _changes(run.store, PAIRS[1]) == {("TRDRISE000000001", d("0.1"), d("0.11")),
                                             ("TRDBACK000000001", d("0.3"), d("0.33"))}
    assert _changes(run.store, PAIRS[2]) == {("TRDBACK000000001", d("0.33"), d("0.3"))}
    # TIER is compared on its first non-zero tier; the reserved price never counts.
    assert _changes(run.store, PAIRS[3]) == {("TRDTIER000000001", d("0.09"), d("0.085")),
                                             ("TRDW2RISE0000001", d("0.12"), d("0.13"))}


def test_counts_are_per_service_key(run):
    run()
    rows = duckdb.sql(
        "SELECT service_key, compared, increased, decreased, excluded, added FROM "
        "read_parquet(?) WHERE location = 'us-east-1' ORDER BY 1",
        params=[str(run.store.pairs_dir / PAIRS[1] / "counts.parquet")],
    ).fetchall()
    by_service = {r[0].split("|")[0]: r[1:] for r in rows}
    assert by_service["AmazonEC2"] == (5, 2, 0, 1, 0)
    assert by_service["AmazonS3"] == (2, 0, 0, 0, 1)
    assert by_service["AWSDataTransfer"] == (1, 0, 0, 0, 0)


def test_a_missing_week_is_a_gap_and_the_pair_spans_it(run):
    run()
    meta = run.store.pair_meta("2026-09-21", "2026-10-05")
    assert meta["gap"] is True
    assert run.store.pair_meta("2026-09-07", "2026-09-14")["gap"] is False
    state = run.store.state()
    assert state["gaps"] == ["2026-09-28"]
    assert state["weeks_built"] == state["weeks_total"] == 4


def test_pair_json_and_state_record_provenance(run):
    run()
    meta = run.store.pair_meta("2026-09-14", "2026-09-21")
    assert (meta["from_snapshot"], meta["to_snapshot"]) == ("2026-09-14 r1", "2026-09-21 r2")
    assert meta["builder_version"] == builder.BUILDER_VERSION and meta["built_at"]
    state = run.store.state()
    assert state["weeks"] == ["2026-09-07 r1", "2026-09-14 r1", "2026-09-21 r2",
                              "2026-10-05 r1", "2026-10-12 r1"]
    assert state["processed"]["2026-09-21"] == 2


def test_only_the_newest_price_list_is_kept(run):
    run()
    assert [p.name for p in run.store.prices_dir.iterdir()] == ["2026-10-12-r1.parquet"]


def test_several_snapshots_in_one_iso_week_use_only_the_latest(root_copy, tmp_path):
    # A second snapshot in the week of 2026-10-12: a copy of that date's manifest, dated 10-14.
    manifests = root_copy / "aws" / "manifests"
    source = json.loads((manifests / "2026-10-12" / "manifest.json").read_text())
    source["snapshot_date"] = "2026-10-14"
    (manifests / "2026-10-14").mkdir()
    (manifests / "2026-10-14" / "manifest.json").write_text(json.dumps(source))
    weeks = select_weeks(list_manifests(LocalStore(root_copy), "aws"))
    assert [w.snapshot_date for w in weeks][-1] in {"2026-10-12", "2026-10-14"}
    assert len(weeks) == 5  # still one per week


def test_a_processed_snapshot_is_never_fetched_again(run):
    run()
    assert len(run.opened) == 5
    run.opened.clear()
    second = run()
    assert run.opened == [] and second.built == []


def test_a_new_revision_rebuilds_the_pairs_on_both_sides(root_copy, tmp_path):
    day = root_copy / "aws" / "manifests" / "2026-09-21"
    current = (day / "manifest.json").read_text()
    shutil.copy(day / "revisions" / "0001.json", day / "manifest.json")
    run = Run(root_copy, tmp_path / "history")
    run()
    assert _counts(run.store, PAIRS[1])["us-east-1"] == (8, 7, 1, 0, 1, 0, 1)  # BACK only

    (day / "manifest.json").write_text(current)  # revision 2 arrives
    run.opened.clear()
    result = run()
    assert sorted(result.built) == [PAIRS[1], PAIRS[2]]
    assert sorted(run.opened) == ["2026-09-14 r1", "2026-09-21 r2", "2026-10-05 r1"]
    assert _counts(run.store, PAIRS[1])["us-east-1"] == EXPECTED[PAIRS[1]]["us-east-1"]


def test_a_builder_version_change_rebuilds_all(run, monkeypatch):
    run()
    monkeypatch.setattr(builder, "BUILDER_VERSION", builder.BUILDER_VERSION + 1)
    run.opened.clear()
    result = run()
    assert sorted(result.built) == PAIRS and len(run.opened) == 5


def test_a_corrupt_file_rebuilds_that_pair(run):
    run()
    (run.store.pairs_dir / PAIRS[2] / "counts.parquet").write_bytes(b"not parquet")
    run.opened.clear()
    result = run()
    assert result.built == [PAIRS[2]]
    assert _counts(run.store, PAIRS[2]) == EXPECTED[PAIRS[2]]


def test_an_interrupted_build_resumes(run, monkeypatch):
    calls = {"n": 0}
    real = builder.build_pair

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("power cut")
        return real(*args, **kwargs)

    monkeypatch.setattr(builder, "build_pair", flaky)
    with pytest.raises(RuntimeError):
        run()
    assert run.store.state()["weeks_built"] == 2
    monkeypatch.setattr(builder, "build_pair", real)
    run.opened.clear()
    result = run()
    assert sorted(result.built) == PAIRS[2:]
    assert "2026-09-07 r1" not in run.opened  # finished pairs aren't redone
