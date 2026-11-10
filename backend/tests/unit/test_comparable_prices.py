"""Comparable price lists for Trends (019, T065, research R10), against the fixtures."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.pricing_data.active_snapshot import get_active_snapshot
from src.pricing_data.providers.base import CatalogItem
from src.pricing_data.providers.registry import get_provider


def _by_key(provider: str):
    rows = get_provider(provider).comparable_prices(get_active_snapshot(provider))
    keys = [(r.location, r.item_key) for r in rows]
    assert len(keys) == len(set(keys)), "one row per (location, item)"
    return {(r.location, r.item_key): r for r in rows}


def test_aws_rows_use_the_first_non_zero_on_demand_tier():
    rows = _by_key("aws")
    egress = rows[("us-west-2", "5M4327XEUKBBTWAT")]
    assert egress.price == Decimal("0.09")  # first of 0.09 / 0.085 / 0.07 / 0.05
    assert egress.tiered is True
    assert egress.service_key == "AWSDataTransfer|Data Transfer"
    t3 = rows[("us-east-1", "NN4EGUUQRWVYP98C")]
    assert t3.service_key == "AmazonEC2|Compute Instance"
    assert t3.service_name == "Amazon Elastic Compute Cloud"
    assert t3.unit == "Hrs" and t3.price > 0 and t3.tiered is False


def test_azure_rows_keep_the_free_tier_out_and_drop_geographies():
    rows = _by_key("azure")
    egress = rows[("eastus", "DZH318Z0BNVX/001D/9995d93a-7d35-4d3f-9c69-7a7fea447ef4")]
    assert egress.price == Decimal("0.087")  # the 100 GB free tier isn't the price
    assert egress.tiered is True
    assert egress.service_key == "Networking|Bandwidth"
    vm = rows[("eastus", "DZH318Z08M9W/004T/db8c0962-f3f8-5b44-99aa-f3c7c1e668c8")]
    assert (vm.price, vm.unit, vm.service_key) == (
        Decimal("0.192"), "1 Hour", "Compute|Virtual Machines")
    # Reservations aren't on-demand prices.
    assert ("eastus", "DZH318Z08M9W/01X9/db8c0962-f3f8-5b44-99aa-f3c7c1e668c8") not in rows
    assert {loc for loc, _ in rows} == {"eastus", "global"}  # north-america is a geography
    assert rows[("global", "DZH318Z0BJTS/0003/6b44a2ed-1103-41f3-90fe-8aaf147c3e41")].price == (
        Decimal("0.4"))


def test_gcp_rows_use_the_default_model_and_taxonomy_keys():
    rows = _by_key("gcp")
    core = rows[("us-east1", "BB77-5FDA-69D9")]
    assert (core.price, core.unit, core.service_key, core.service_name) == (
        Decimal("0.031611"), "h", "Compute|GCE", "Compute Engine")
    assert rows[("us-east1", "F274-1692-F213")].price == Decimal("0.12")
    assert rows[("global", "92D2-8A8F-DF54")].price == Decimal("0.046")


def test_zero_prices_are_kept_for_the_builder_to_exclude():
    # Every tier of Azure's DevTest licence row is 0, but that's not Consumption; the free
    # GCP storage tier is the first of two, so the US regional storage price is its second.
    assert _by_key("gcp")[("us-east1", "E5F0-6A5D-7BAD")].price == Decimal("0.02")


@pytest.mark.parametrize(
    ("provider", "item", "key"),
    [
        ("aws", CatalogItem("aws", "AmazonEC2", None, "Compute Instance", "S", "", {}, None),
         "AmazonEC2|Compute Instance"),
        ("azure", CatalogItem("azure", "X", "Bandwidth", "Rtn Preference: MGN", "S", "",
                              {"service_family": "Networking"}, None), "Networking|Bandwidth"),
        ("gcp", CatalogItem("gcp", "X", None, "Compute > GCE > VMs On Demand", "S", "", {},
                            None), "Compute|GCE"),
    ],
)
def test_service_key_per_item(provider, item, key):
    assert get_provider(provider).service_key(item) == key
