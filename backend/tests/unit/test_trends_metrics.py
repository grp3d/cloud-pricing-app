"""SKUs Changed and price movers (019, T067, T083, FR-012 to FR-019, data-model §8)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.pricing_data.history.metrics import movers, skus_changed
from src.pricing_data.history.store import HistoryStore
from src.services.categories import Categorizer, Rule
from tests.helpers.history import build_trends_history, write_pair, write_prices

RULES = Categorizer([
    Rule("aws", "service_code", "AmazonEC2", "compute", 0),
    Rule("aws", "service_code", "AmazonS3", "storage", 0),
    Rule("gcp", "taxonomy_1", "Compute", "compute", 0),
])


def _keys(category):
    return None if category == "all" else (lambda present: RULES.keys_for("aws", category, present))


@pytest.fixture(scope="module")
def history(tmp_path_factory):
    return build_trends_history(tmp_path_factory.mktemp("history"))


def _tuples(points):
    return [(p.week, p.increased, p.decreased, p.compared, p.excluded, p.gap) for p in points]


def test_sums_over_the_selected_regions(history):
    assert _tuples(skus_changed(history, regions=["us-east-1", "us-west-2"])) == [
        ("2026-09-14", 0, 1, 10, 1, False),
        ("2026-09-21", 2, 0, 10, 1, False),
        ("2026-10-05", 0, 1, 10, 1, True),
        ("2026-10-12", 1, 1, 10, 1, False),
    ]


def test_empty_regions_mean_all_regions(history):
    assert _tuples(skus_changed(history, regions=[])) == _tuples(
        skus_changed(history, regions=["us-east-1", "us-west-2"]))


def test_percentages_are_of_compared_and_points_keep_provenance(history):
    last = skus_changed(history, regions=[])[-1]
    assert (last.increased_pct, last.decreased_pct) == (10.0, 10.0)
    assert (last.from_snapshot, last.to_snapshot) == ("2026-10-05 r1", "2026-10-12 r1")
    second = skus_changed(history, regions=[])[1]
    assert second.to_snapshot == "2026-09-21 r2"


def test_no_changes_is_zero_not_no_data(history):
    first = skus_changed(history, regions=["us-west-2"])[0]
    assert (first.increased, first.decreased, first.increased_pct, first.compared) == (
        0, 0, 0.0, 2)


def test_nothing_compared_is_no_data(history):
    point = skus_changed(history, regions=["us-west-2"], keys=_keys("storage"))[0]
    assert (point.increased, point.decreased, point.increased_pct, point.compared,
            point.excluded) == (None, None, None, None, None)


def test_a_category_counts_only_its_service_keys(history):
    compute = skus_changed(history, regions=["us-east-1"], keys=_keys("compute"))
    assert [(p.compared, p.increased, p.decreased, p.excluded) for p in compute] == [
        (5, 0, 1, 1), (5, 2, 0, 1), (5, 0, 1, 1), (5, 0, 0, 1)]
    storage = skus_changed(history, regions=["us-east-1"], keys=_keys("storage"))
    assert [p.compared for p in storage] == [2, 2, 2, 2]


def test_uncategorized_services_count_only_under_all(history):
    # AWSDataTransfer has no rule: its TIER decrease (10-05 → 10-12) is only in "all".
    everything = skus_changed(history, regions=["us-east-1"])[-1]
    named = [skus_changed(history, regions=["us-east-1"], keys=_keys(c))[-1]
             for c in ("compute", "storage", "database", "networking")]
    assert everything.decreased == 1
    assert sum(p.decreased or 0 for p in named) == 0
    assert everything.compared == sum(p.compared or 0 for p in named) + 1


def test_global_counts_once_per_provider_and_multi_regional_per_region(tmp_path):
    store = HistoryStore(tmp_path, "gcp")
    write_pair(store, "2026-10-05", "2026-10-12", [
        ("us-east1", "Compute|GCE", 4, 1, 0, 0),   # a multi-regional SKU filed in both regions
        ("us-west1", "Compute|GCE", 4, 1, 0, 0),
        ("europe-west1", "Compute|GCE", 9, 9, 0, 0),
        ("global", "Other|Licenses", 2, 0, 1, 0),  # global-only
    ])
    two = skus_changed(store, regions=["us-east1", "us-west1"])[0]
    assert (two.compared, two.increased, two.decreased) == (10, 2, 1)
    one = skus_changed(store, regions=["us-west1"])[0]
    assert (one.compared, one.increased, one.decreased) == (6, 1, 1)
    every = skus_changed(store, regions=[])[0]
    assert (every.compared, every.increased) == (19, 11)


def test_weeks_are_limited_to_52(tmp_path):
    store = HistoryStore(tmp_path, "aws")
    start = date(2025, 6, 2)
    for i in range(56):
        a, b = start + timedelta(weeks=i), start + timedelta(weeks=i + 1)
        write_pair(store, a.isoformat(), b.isoformat(), [("us-east-1", "X|Y", 1, 0, 0, 0)])
    points = skus_changed(store, regions=[])
    assert len(points) == 52
    assert points[-1].week == (start + timedelta(weeks=56)).isoformat()
    assert len(skus_changed(store, regions=[], weeks=4)) == 4


# --- Price movers (T083, FR-016 to FR-019) ---------------------------------------------------


def _entries(entries):
    return [(m.item_key, m.region, str(m.start_price), str(m.end_price), m.change_pct)
            for m in entries]


def test_movers_over_the_whole_history_match_the_fixture(history):
    result = movers(history, regions=[], period_weeks=52)
    assert _entries(result.increases) == [
        ("TRDRISE000000001", "us-east-1", "0.1", "0.11", 10.0),
        ("TRDW2RISE0000001", "us-west-2", "0.12", "0.13", 8.33),
    ]
    # BACK (0.30 -> 0.33 -> 0.30) changed and changed back, so it is dropped.
    assert _entries(result.decreases) == [
        ("TRDFALL000000001", "us-east-1", "0.2", "0.18", -10.0),
        ("TRDTIER000000001", "us-east-1", "0.09", "0.085", -5.56),
    ]
    # History is shorter than the period: 5 weeks, 09-07 to 10-12.
    assert (result.from_snapshot, result.to_snapshot, result.weeks_available) == (
        "2026-09-07 r1", "2026-10-12 r1", 5)


def test_movers_entries_carry_what_the_list_shows(history):
    result = movers(history, regions=[], period_weeks=52)
    rise = result.increases[0]
    assert rise.service_name and rise.description and rise.unit
    assert rise.tier_note is None
    tier = result.decreases[1]
    assert tier.tier_note == "Compared on the first non-zero tier"


def test_the_period_is_the_newest_weeks(history):
    week = movers(history, regions=[], period_weeks=1)
    assert [m.item_key for m in week.increases] == ["TRDW2RISE0000001"]
    assert [m.item_key for m in week.decreases] == ["TRDTIER000000001"]
    assert (week.from_snapshot, week.weeks_available) == ("2026-10-05 r1", 1)
    # 4 weeks back from 10-12 is 09-14: FALL (09-07 -> 09-14) is outside it.
    month = movers(history, regions=[], period_weeks=4)
    assert [m.item_key for m in month.increases] == ["TRDRISE000000001", "TRDW2RISE0000001"]
    assert [m.item_key for m in month.decreases] == ["TRDTIER000000001"]
    assert (month.from_snapshot, month.weeks_available) == ("2026-09-14 r1", 4)


def test_movers_by_region_and_category(history):
    west = movers(history, regions=["us-west-2"], period_weeks=52)
    assert [m.item_key for m in west.increases] == ["TRDW2RISE0000001"]
    assert west.decreases == []
    compute = movers(history, regions=[], keys=_keys("compute"), period_weeks=52)
    # TIER is AWSDataTransfer, uncategorized here: only under "all categories".
    assert [m.item_key for m in compute.decreases] == ["TRDFALL000000001"]
    storage = movers(history, regions=[], keys=_keys("storage"), period_weeks=52)
    assert (storage.increases, storage.decreases) == ([], [])


def test_no_history_gives_no_result(tmp_path):
    assert movers(HistoryStore(tmp_path, "aws"), regions=[], period_weeks=52) is None


def _change(loc, key, old, new, *, name="Svc", desc=None, service_key="Compute|GCE",
            tiered=False):
    return (loc, key, service_key, name, desc or key, "h", tiered, old, new)


def _price(loc, key, price, *, name="Svc", desc=None, service_key="Compute|GCE"):
    return (loc, key, service_key, name, desc or key, "h", price, False)


def test_items_removed_before_the_end_are_dropped(tmp_path):
    store = HistoryStore(tmp_path, "gcp")
    write_pair(store, "2026-10-05", "2026-10-12", [], changes=[
        _change("us-east1", "GONE", "1.00", "2.00"),
        _change("us-east1", "KEPT", "1.00", "1.50"),
    ])
    write_pair(store, "2026-10-12", "2026-10-19", [])
    write_prices(store, "2026-10-19", [_price("us-east1", "KEPT", "1.50")])
    result = movers(store, regions=[], period_weeks=52)
    assert [m.item_key for m in result.increases] == ["KEPT"]


def test_global_counts_once_and_a_sku_in_two_regions_is_two_entries(tmp_path):
    store = HistoryStore(tmp_path, "gcp")
    write_pair(store, "2026-10-05", "2026-10-12", [], changes=[
        _change("us-east1", "MULTI", "1.00", "1.20"),
        _change("us-west1", "MULTI", "1.00", "1.20"),
        _change("global", "LICENSE", "2.00", "2.50"),
        _change("europe-west1", "FAR", "1.00", "3.00"),
    ])
    write_prices(store, "2026-10-12", [
        _price("us-east1", "MULTI", "1.20"), _price("us-west1", "MULTI", "1.20"),
        _price("global", "LICENSE", "2.50"), _price("europe-west1", "FAR", "3.00"),
    ])
    result = movers(store, regions=["us-east1", "us-west1"], period_weeks=52)
    assert [(m.item_key, m.region) for m in result.increases] == [
        ("LICENSE", "global"), ("MULTI", "us-east1"), ("MULTI", "us-west1")]


def test_ties_rank_by_price_change_then_name_and_keep_three(tmp_path):
    store = HistoryStore(tmp_path, "aws")
    rows = [  # all +10%
        _change("us-east-1", "SMALL", "1.00", "1.10", name="B"),
        _change("us-east-1", "BIG", "2.00", "2.20", name="Z"),
        _change("us-east-1", "B-NAME", "1.00", "1.10", name="A"),
        _change("us-east-1", "LAST", "1.00", "1.10", name="C"),
    ]
    write_pair(store, "2026-10-05", "2026-10-12", [], changes=rows)
    write_prices(store, "2026-10-12", [_price(r[0], r[1], r[8], name=r[3]) for r in rows])
    result = movers(store, regions=[], period_weeks=52)
    assert [m.item_key for m in result.increases] == ["BIG", "B-NAME", "SMALL"]


def test_start_is_before_the_first_change_and_end_after_the_last(tmp_path):
    store = HistoryStore(tmp_path, "aws")
    write_pair(store, "2026-10-05", "2026-10-12", [],
               changes=[_change("us-east-1", "X", "1.00", "1.20")])
    write_pair(store, "2026-10-12", "2026-10-19", [],
               changes=[_change("us-east-1", "X", "1.20", "0.90")])
    write_prices(store, "2026-10-19", [_price("us-east-1", "X", "0.90")])
    result = movers(store, regions=[], period_weeks=52)
    assert result.increases == []
    assert _entries(result.decreases) == [("X", "us-east-1", "1", "0.9", -10.0)]
