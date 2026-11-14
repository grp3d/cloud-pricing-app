"""Pricing comparisons (024, research R5, FR-001, FR-004, FR-011, FR-012, SC-007): every amount
is the engine's, differences come from unrounded values, totals cover only rows priced on every
side and are labelled partial otherwise, and nothing is saved."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from src.agent.compare import (
    TERMS,
    Cell,
    PriceLine,
    Row,
    Side,
    price_comparison,
    price_lines,
    term_option,
)
from src.agent.operations import ToolError
from src.models.orm import Architecture
from src.models.schemas import CalculationDuration, SnapshotSelection
from src.pricing_data.active_snapshot import get_active_snapshot
from src.pricing_data.providers.registry import get_provider
from src.services.price_calculation import (
    build_transient_architecture,
    calculate_architecture_price,
)
from tests.helpers.agent import DEFAULT_PRICING_ROOT, combined_pricing_root

# Fixture items (tests/fixtures/pricing_parquet*): S3 Standard and RDS in us-east-1; Azure Hot LRS
# blob and D4s_v5 in eastus; GCP Standard storage and an E2 core in us-east1.
S3 = ("AmazonS3", "WP9ANXZGBYYSGJEA")
AZ_BLOB = ("DZH317F1HKN0", "DZH318Z0BPH7/006M/272492b3-1c92-4a5f-bee9-52a8e10ca514")
GCP_STD = ("95FF-2EF5-5EA1", "E5F0-6A5D-7BAD")


@pytest.fixture(autouse=True)
def _all_providers(use_pricing_root):
    use_pricing_root(combined_pricing_root())


def _engine(provider, region, item, quantity, term="on_demand", option="not_applicable",
            options=None, duration="1_month") -> Decimal:
    arch = build_transient_architecture([SnapshotSelection(
        service_code=item[0], sku=item[1], pricing_term=term, purchase_option=option,
        usage_quantity=quantity, region=region, provider_options=options)], provider=provider)
    return calculate_architecture_price(arch, CalculationDuration(duration)).total_price


def _line(key, item, region, quantity, term="on_demand", option="not_applicable", options=None):
    return PriceLine(key, item[0], item[1], region, Decimal(quantity), term, option, options)


def _storage_comparison(azure_line=True, duration="1_month"):
    sides = [Side("aws:us-east-1", "aws", "us-east-1", False, "on_demand", "not_applicable"),
             Side("azure:eastus", "azure", "eastus", True, "on_demand", "not_applicable"),
             Side("gcp:us-east1", "gcp", "us-east1", True, "on_demand", "not_applicable")]
    rows = [Row("Object storage", "VPC", {
        "aws:us-east-1": Cell(product="S3", line=_line("r1", S3, "us-east-1", 2000)),
        "azure:eastus": (Cell(product="Blob", quality="close",
                              line=_line("r1", AZ_BLOB, "eastus", 2000)) if azure_line
                         else Cell(status="unmatched", reason="no product in the same category")),
        "gcp:us-east1": Cell(product="GCS", quality="exact",
                             line=_line("r1", GCP_STD, "us-east1", 2000)),
    })]
    return price_comparison(sides, rows, duration)


@pytest.mark.parametrize("duration", ["1_day", "1_month", "1_year"])
def test_amounts_are_the_engines_and_differences_unrounded(duration):
    outcome = _storage_comparison(duration=duration)
    cells = outcome.rows[0].cells
    aws = _engine("aws", "us-east-1", S3, 2000, duration=duration)
    azure = _engine("azure", "eastus", AZ_BLOB, 2000, duration=duration)
    gcp = _engine("gcp", "us-east1", GCP_STD, 2000, duration=duration)
    assert (cells["aws:us-east-1"].amount, cells["azure:eastus"].amount,
            cells["gcp:us-east1"].amount) == (aws, azure, gcp)
    assert cells["azure:eastus"].diff == azure - aws
    assert cells["azure:eastus"].diff_pct == (azure - aws) / aws * 100
    assert cells["aws:us-east-1"].diff is None  # the reference side
    assert outcome.totals["gcp:us-east1"] == {"amount": gcp, "partial": False, "diff": gcp - aws,
                                              "diff_pct": (gcp - aws) / aws * 100}
    assert set(outcome.snapshots) == {"aws", "azure", "gcp"}


def test_an_unmatched_row_has_no_figures_and_makes_totals_partial():
    outcome = _storage_comparison(azure_line=False)
    cell = outcome.rows[0].cells["azure:eastus"]
    assert (cell.status, cell.amount, cell.diff, cell.diff_pct) == ("unmatched", None, None, None)
    for side in ("aws:us-east-1", "azure:eastus", "gcp:us-east1"):
        assert outcome.totals[side]["partial"] is True
        assert outcome.totals[side]["amount"] is None  # no row is priced on every side
    assert outcome.not_compared == ["Object storage (AZURE: no product in the same category)"]


def test_a_side_without_pricing_data_is_unavailable():
    sides = [Side("aws:us-east-1", "aws", "us-east-1", False, "on_demand", "not_applicable"),
             Side("gcp:asia-east1", "gcp", "asia-east1", False, "on_demand", "not_applicable",
                  available=False, reason="no GCP pricing data for asia-east1")]
    rows = [Row("Object storage", None, {
        "aws:us-east-1": Cell(line=_line("r1", S3, "us-east-1", 100))})]
    outcome = price_comparison(sides, rows, "1_month")
    cell = outcome.rows[0].cells["gcp:asia-east1"]
    assert (cell.status, cell.amount, cell.reason) == (
        "unavailable", None, "no GCP pricing data for asia-east1")
    assert outcome.rows[0].cells["aws:us-east-1"].amount is not None


def test_a_term_the_product_doesnt_publish_is_unavailable():
    # Blob storage publishes on-demand only (fixture price_types).
    priced = price_lines("azure", [_line("r1", AZ_BLOB, "eastus", 100, "savings_plan_1yr")],
                         "1_month")
    assert "r1" not in priced.amounts and priced.reasons["r1"]


def _publishing(provider, region, term, option):
    """A fixture item that publishes `term`, or None."""
    adapter = get_provider(provider)
    snap = get_active_snapshot(provider)
    searches = ([{"service_code": "AmazonEC2", "product_family": "Compute Instance"},
                 {"service_code": "AmazonRDS", "product_family": "Database Instance"}]
                if provider == "aws" else [{"kind": "vm"}, {"kind": "managed_db"}])
    for filters in searches:
        items, _ = adapter.search(snap, region=region, limit=200, offset=0, **filters)
        for item in items:
            if provider == "aws":
                if adapter.units(snap, [(item.sku, term, option)], region=region).get(
                        (item.sku, term, option)):
                    return item
            elif term in item.price_types and not item.attributes.get("ram_sku"):
                return item
    return None


@pytest.mark.parametrize(("provider", "region", "term", "option"), [
    *[("aws", "us-east-1", t, o) for t in TERMS["aws"] for o in
      (("not_applicable",) if t == "on_demand" else ("no_upfront", "partial_upfront",
                                                     "all_upfront"))],
    *[("azure", "eastus", t, "not_applicable") for t in TERMS["azure"]],
    *[("gcp", "us-east1", t, "not_applicable") for t in TERMS["gcp"]],
])
def test_every_fr004_term_maps_and_prices_like_the_engine(provider, region, term, option,
                                                         use_pricing_root):
    # The default fixture holds each provider's reservation, savings-plan and commitment rows.
    use_pricing_root(DEFAULT_PRICING_ROOT)
    assert term_option(provider, term, None if option == "not_applicable" else option) == (
        term, option)
    item = _publishing(provider, region, term, option)
    if item is None:
        pytest.skip(f"no {provider} fixture item publishes {term}/{option}")
    options = {"kind": "azure_vm", "version": 1, "os": "linux"} if (
        provider == "azure" and item.kind == "vm") else None
    priced = price_lines(provider, [_line("r1", (item.service_code, item.sku), region, 24, term,
                                          option, options)], "1_month")
    expected = _engine(provider, region, (item.service_code, item.sku), 24, term, option, options)
    assert priced.amounts["r1"] == expected


def test_term_option_refuses_terms_a_provider_doesnt_have():
    with pytest.raises(ToolError, match="isn't a GCP pricing term"):
        term_option("gcp", "savings_plan_1yr", None)
    assert term_option("aws", "reserved_1yr", None) == ("reserved_1yr", "no_upfront")


async def test_nothing_is_saved(db_session):
    before = (await db_session.execute(select(func.count()).select_from(Architecture))).scalar()
    _storage_comparison()
    await db_session.flush()
    after = (await db_session.execute(select(func.count()).select_from(Architecture))).scalar()
    assert after == before
    assert not db_session.new
