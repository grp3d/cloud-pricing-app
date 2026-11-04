"""The Azure adapter against the T004 fixture (019, T032; research R4 to R8). Expected prices are
the fixture README's."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.pricing_data.active_snapshot import get_active_snapshot
from src.pricing_data.providers.azure import AzureProvider
from src.pricing_data.providers.tiers import normalize_tiers, price_for_duration

VM_LINUX = "DZH318Z08M9W/004T/db8c0962-f3f8-5b44-99aa-f3c7c1e668c8"
VM_WINDOWS = "DZH318Z08M9T/00CS/57bde05c-423b-50c9-8e57-d668c0481cce"
DISK_P10 = "DZH318Z0BP04/0035/93a6a529-4f49-47cb-9b1e-db9e5f23263f"
EGRESS_MGN = "DZH318Z0BNVX/001D/9995d93a-7d35-4d3f-9c69-7a7fea447ef4"
DUP_METER = "DZH318Z0BPH7/006M/14854f12-8d37-4299-842a-b0f2df82a305"
SQL_LICENCE = "DZH318Z0BJTS/0003/6b44a2ed-1103-41f3-90fe-8aaf147c3e41"
VM_SERVICE = "DZH313Z7MMC8"

azure = AzureProvider()


@pytest.fixture
def snap():
    return get_active_snapshot("azure")


def _price(snap, item, term="on_demand", **kw):
    return azure.price(snap, item=item, pricing_term=term,
                       purchase_option=kw.pop("purchase_option", "not_applicable"),
                       region="eastus", **kw)


def test_locations_exclude_global_and_geographies(snap):
    assert azure.locations(snap) == ["eastus"]
    assert azure.display_names(snap) == {"eastus": "US East"}


def test_search_returns_region_and_global_items(snap):
    items, total = azure.search(snap, region="eastus", limit=50, offset=0, text="SQL Server")
    assert total == 1
    (licence,) = items
    assert licence.sku == SQL_LICENCE
    assert licence.location_scope == "global"
    assert licence.price_types == ("on_demand", "savings_plan_1yr", "savings_plan_3yr")

    items, _ = azure.search(snap, region="eastus", limit=50, offset=0, text="D4s v5")
    assert {i.location_scope for i in items} == {"regional"}


def test_geography_items_are_never_returned(snap):
    items, total = azure.search(snap, region="eastus", limit=50, offset=0, text="Bandwidth Alliance")
    assert (items, total) == ([], 0)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("vm", {VM_LINUX}),
        ("block_storage", {DISK_P10}),
        ("object_storage", {"DZH318Z0BPH7/006M/272492b3-1c92-4a5f-bee9-52a8e10ca514"}),
        ("data_transfer", {EGRESS_MGN, "DZH318Z0C8ZQ/000K/6bd64e8e-5cb9-49d3-893d-800c9b28dca3"}),
        ("managed_db", {"DZH318Z0KDZJ/00D3/71f7052a-b259-5928-b57b-d6fbbc1c8cd1"}),
    ],
)
def test_kind_filters_match_the_reference_lookups(snap, kind, expected):
    items, total = azure.search(snap, region="eastus", limit=50, offset=0, kind=kind)
    assert {i.sku for i in items} == expected
    assert total == len(expected)
    assert {i.kind for i in items} == {kind}


def test_vm_item_publishes_every_azure_price_type(snap):
    (vm,) = azure.describe(snap, [(VM_SERVICE, VM_LINUX)], region="eastus").values()
    assert vm.price_types == ("on_demand", "reserved_1yr", "reserved_3yr",
                              "savings_plan_1yr", "savings_plan_3yr")
    assert vm.unit == "1 Hour"
    assert vm.attributes["arm_sku_name"] == "Standard_D4s_v5"


def test_describe_and_exists(snap):
    keys = [(VM_SERVICE, VM_LINUX), (VM_SERVICE, "NOPE/0000/none"), ("other", VM_LINUX)]
    assert set(azure.describe(snap, keys, region="eastus")) == {(VM_SERVICE, VM_LINUX)}
    assert azure.exists(snap, keys, region="eastus") == {(VM_SERVICE, VM_LINUX)}


def test_on_demand_vm(snap):
    quote = _price(snap, VM_LINUX)
    assert [t.rate for t in quote.tiers] == [Decimal("0.192")]
    cost = price_for_duration(normalize_tiers(quote.tiers), Decimal(730) / 31, quote.unit, 31,
                              quote.unit_class)
    assert cost.cost == pytest.approx(Decimal("140.16"), abs=Decimal("1e-20"))


def test_azure_vm_option_picks_the_windows_or_linux_meter(snap):
    windows = _price(snap, VM_LINUX, options={"kind": "azure_vm", "version": 1, "os": "windows"})
    assert [t.rate for t in windows.tiers] == [Decimal("0.376")]
    linux = _price(snap, VM_WINDOWS, options={"kind": "azure_vm", "version": 1, "os": "linux"})
    assert [t.rate for t in linux.tiers] == [Decimal("0.192")]


def test_reservation_is_an_upfront_fee_with_no_recurring_rate(snap):
    one = _price(snap, VM_LINUX, "reserved_1yr")
    three = _price(snap, VM_LINUX, "reserved_3yr")
    assert (one.upfront_fee, one.recurring_rate) == (Decimal("1038.0"), Decimal(0))
    assert three.upfront_fee == Decimal("1993.0")
    assert one.tiers == []


def test_savings_plan_prices_from_the_savings_plan_table(snap):
    assert [t.rate for t in _price(snap, VM_LINUX, "savings_plan_1yr").tiers] == [
        Decimal("0.1316736")
    ]
    assert [t.rate for t in _price(snap, VM_LINUX, "savings_plan_3yr").tiers] == [
        Decimal("0.0883584")
    ]


def test_unpublished_price_types_are_none(snap):
    assert _price(snap, DISK_P10, "reserved_1yr") is None
    assert _price(snap, DISK_P10, "savings_plan_1yr") is None
    assert _price(snap, VM_LINUX, "commitment_1yr") is None
    # The Windows meter has no reservation in the fixture.
    assert _price(snap, VM_LINUX, "reserved_1yr",
                  options={"kind": "azure_vm", "version": 1, "os": "windows"}) is None


def test_egress_500_gb_uses_the_free_tier_then_the_next(snap):
    quote = _price(snap, EGRESS_MGN)
    tiers = normalize_tiers(quote.tiers)
    assert [(t.start_quantity, t.rate) for t in tiers][:2] == [
        (Decimal(0), Decimal("0.0")), (Decimal(100), Decimal("0.087"))
    ]
    # 500 GB a month: a no-period unit is a daily amount, so 500/31 per day for 31 days.
    month = price_for_duration(tiers, Decimal(500) / 31, quote.unit, 31, quote.unit_class)
    assert month.cost == pytest.approx(Decimal("34.80"), abs=Decimal("1e-20"))
    assert [p.rate for p in month.parts] == [Decimal("0.0"), Decimal("0.087")]


def test_the_duplicate_name_meter_collapses_to_one_tier(snap):
    quote = _price(snap, DUP_METER)
    assert len(quote.tiers) == 2
    assert normalize_tiers(quote.tiers) == [quote.tiers[0]]
    # `10K` is a block of 10,000 operations: the rate is per operation.
    assert quote.tiers[0].rate == Decimal("0.05") / 10_000
    (item,) = azure.describe(snap, [("DZH317F1HKN0", DUP_METER)], region="eastus").values()
    assert item.unit == "10K"


def test_a_purchase_option_is_never_used_for_azure(snap):
    assert _price(snap, VM_LINUX, purchase_option="all_upfront") is None


def test_global_items_price_from_any_region(snap):
    assert [t.rate for t in _price(snap, SQL_LICENCE).tiers] == [Decimal("0.4")]
