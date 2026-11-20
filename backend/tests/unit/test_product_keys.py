"""Product keys (026, research R2): a kind of product has the same key in every region, and
`find_by_key` finds that product's row in another region, or nothing when it isn't sold there."""

from __future__ import annotations

import pytest

from src.pricing_data.active_snapshot import get_active_snapshot
from src.pricing_data.providers import keys
from src.pricing_data.providers.registry import get_provider
from tests.helpers.agent import combined_pricing_root


@pytest.fixture(autouse=True)
def _combined(use_pricing_root):
    use_pricing_root(combined_pricing_root())


def _item(provider: str, region: str, service_code: str, sku: str):
    adapter = get_provider(provider)
    found = adapter.describe(get_active_snapshot(provider), [(service_code, sku)], region=region)
    return found[(service_code, sku)]


# --- Pure key rules ------------------------------------------------------------------------------


@pytest.mark.parametrize(("usage_type", "expected"), [
    ("USW2-BoxUsage:t4g.xlarge", "BoxUsage:t4g.xlarge"),
    ("BoxUsage:t4g.xlarge", "BoxUsage:t4g.xlarge"),          # us-east-1 has no prefix
    ("EU-Request-ARM", "Request-ARM"),
    ("USE1-USW2-AWS-Out-Bytes", "USW2-AWS-Out-Bytes"),      # only the item's own region
    ("Storage-ShardHour", "Storage-ShardHour"),             # not a region prefix
    ("Aurora:StorageUsage", "Aurora:StorageUsage"),
])
def test_aws_usage_type_loses_only_its_region_prefix(usage_type, expected):
    assert keys.aws_usage_type(usage_type) == expected


@pytest.mark.parametrize(("name", "expected"), [
    ("E2 Instance Core running in Americas", "E2 Instance Core running"),
    ("E2 Instance Core running in EMEA", "E2 Instance Core running"),
    ("E2 Instance Core running in Northern Virginia", "E2 Instance Core running"),
    ("Regional External Application Load Balancer Forwarding Rule Minimum for South Carolina "
     "(us-east1)", "Regional External Application Load Balancer Forwarding Rule Minimum"),
    ("Analysis (europe-west1)", "Analysis"),
    ("Cloud Run functions Memory (Request-based billing) in europe-west1",
     "Cloud Run functions Memory (Request-based billing)"),
    ("Coldline Storage South Carolina", "Coldline Storage"),
    ("Coldline Storage Belgium", "Coldline Storage"),
    ("Coldline Storage Belgium Dual-region", "Coldline Storage {L} Dual-region"),
    ("Coldline Storage Belgium (Early Delete)", "Coldline Storage (Early Delete)"),
    ("Redis Capacity Standard M2 Iowa/South Carolina/Oregon", "Redis Capacity Standard M2"),
    ("Standard Storage US Regional", "Standard Storage"),
    ("Network Inter Region Data Transfer Out from Americas to Americas",
     "Network Inter Region Data Transfer Out from {L} to {L}"),
    ("Cloud Firestore Read Ops", "Cloud Firestore Read Ops"),
])
def test_gcp_name_loses_its_location_words(name, expected):
    assert keys.gcp_name(name) == expected


# --- Keys over real fixture rows -----------------------------------------------------------------


def test_aws_key_is_the_same_in_two_regions():
    east = _item("aws", "us-east-1", "AmazonEC2", _aws_sku("us-east-1", "BoxUsage:t4g.xlarge"))
    west = _item("aws", "us-west-2", "AmazonEC2", _aws_sku("us-west-2", "USW2-BoxUsage:t4g.xlarge"))
    adapter = get_provider("aws")
    assert adapter.product_key(east) == adapter.product_key(west)
    other = _item("aws", "us-west-2", "AmazonEC2", _aws_sku("us-west-2", "USW2-BoxUsage:m6i.large"))
    assert adapter.product_key(other) != adapter.product_key(west)


def test_gcp_key_is_the_same_in_two_regions():
    adapter = get_provider("gcp")
    east = _item("gcp", "us-east1", "E505-1604-58F8", "5D5C-9D70-6B3E")
    west = _item("gcp", "us-west1", "E505-1604-58F8", "0E91-5E0F-9B98")
    assert east.sku != west.sku
    assert adapter.product_key(east) == adapter.product_key(west)


def test_azure_key_is_the_same_in_two_regions():
    adapter = get_provider("azure")
    snapshot = get_active_snapshot("azure")
    rows = {}
    for region in ("eastus", "westus2"):
        found, _total = adapter.search(snapshot, region=region, limit=50, offset=0,
                                       text="Standard_D4s_v5")
        rows[region] = next(r for r in found if r.attributes.get("meter_name") == "D4s v5"
                            and "Windows" not in r.summary and "Spot" not in r.summary
                            and "Low Priority" not in r.summary)
    assert rows["eastus"].sku != rows["westus2"].sku
    assert adapter.product_key(rows["eastus"]) == adapter.product_key(rows["westus2"])


# --- find_by_key ---------------------------------------------------------------------------------


def test_find_by_key_returns_the_other_regions_row():
    adapter = get_provider("gcp")
    east = _item("gcp", "us-east1", "E505-1604-58F8", "5D5C-9D70-6B3E")
    found = keys.find_by_key(adapter, get_active_snapshot("gcp"), "us-west1",
                             adapter.product_key(east), east.service_code)
    assert found is not None and found.sku == "0E91-5E0F-9B98"


def test_find_by_key_is_none_where_the_product_isnt_sold():
    adapter = get_provider("gcp")
    item = _item("gcp", "us-west1", "CCD8-9BF1-090E", "1C7A-489D-CCD0")  # Autopilot mCPU
    assert keys.find_by_key(adapter, get_active_snapshot("gcp"), "europe-west1",
                            adapter.product_key(item), item.service_code) is None


def _aws_sku(region: str, usage_type: str) -> str:
    adapter = get_provider("aws")
    found, _total = adapter.search(get_active_snapshot("aws"), region=region, limit=200,
                                   offset=0, service_code="AmazonEC2",
                                   product_family="Compute Instance")
    for item in found:
        if item.attributes.get("usagetype") == usage_type and \
                item.attributes.get("operation") == "RunInstances":
            return item.sku
    raise AssertionError(f"{usage_type} not in the {region} fixture")


# --- Ties (026): several rows with one key ------------------------------------------------------


class _FakeAzure:
    code = "azure"

    def __init__(self, rows):
        self.rows = rows

    def search(self, _snapshot, *, region, limit, offset, **_filters):
        return self.rows[offset:offset + limit], len(self.rows)

    def product_key(self, item):
        return keys.azure_key(item)


def _azure_row(sku: str, location: str):
    from src.pricing_data.providers.base import CatalogItem

    return CatalogItem(provider="azure", service_code="S", service_name="Functions",
                       product_family="Functions", sku=sku, summary="",
                       attributes={"product_name": "Functions", "sku_name": "Standard",
                                   "meter_name": "Standard Total Executions",
                                   "location": location}, unit="10")


def test_the_regions_own_row_wins_over_a_wider_geographys():
    rows = [_azure_row("PROD/000D/meter", "europe"), _azure_row("PROD/0013/meter", "uksouth")]
    key = keys.azure_key(rows[0])
    found, why = keys.resolve_key(_FakeAzure(rows), None, "uksouth", key)
    assert why is None and found.sku == "PROD/0013/meter"


def test_rows_nothing_tells_apart_are_ambiguous_never_guessed():
    rows = [_azure_row("PROD/000D/meter", "uksouth"), _azure_row("PROD/0013/meter", "uksouth")]
    key = keys.azure_key(rows[0])
    assert keys.resolve_key(_FakeAzure(rows), None, "uksouth", key) == (None, keys.AMBIGUOUS)
    assert keys.resolve_key(_FakeAzure([]), None, "uksouth", key) == (None, keys.MISSING)
