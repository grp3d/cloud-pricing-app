"""SKUs Changed (019, T067, FR-012 to FR-015a, data-model §8)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.pricing_data.history.metrics import skus_changed
from src.pricing_data.history.store import HistoryStore
from src.services.categories import Categorizer, Rule
from tests.helpers.history import build_trends_history, write_pair

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
