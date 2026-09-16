"""Integration test for duration-scoped pricing across a mixed Architecture
(004-canvas-pricing-improvements, FR-001, FR-002, FR-003, quickstart.md step 2;
006-fix-reserved-pricing, FR-001-FR-005, quickstart.md Scenarios 1-4).

Runs against the real Parquet pricing data (Constitution Principle I — no mock substitute).
"""

from decimal import Decimal

import pytest

# Real SKUs confirmed during implementation: an on-demand Hrs-family EC2 instance, and a
# Reserved-1yr EC2 instance with a real partial-upfront recurring rate.
ON_DEMAND_SKU = "NN4EGUUQRWVYP98C"
RESERVED_SKU = "QZ9R39S2Y8MCC9Y8"
SERVICE_CODE = "AmazonEC2"

# The exact SKU from the 006-fix-reserved-pricing bug report — used for exact-dollar-figure
# assertions (spec.md's Input, quickstart.md Scenarios 1-3), distinct from RESERVED_SKU above
# (which the existing 004 tests already use for looser, relative-scaling checks).
BUG_REPORT_SKU = "2THCJ54S3VW8G6VS"


async def _create_collection(client, auth_headers) -> tuple[str, str]:
    arch = await client.post(
        "/api/v1/architectures",
        json={"name": "Duration Mix", "provider": "aws"},
        headers=auth_headers,
    )
    arch_id = arch.json()["id"]
    coll = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "Mixed", "region": "us-east-1"},
        headers=auth_headers,
    )
    return arch_id, coll.json()["id"]


@pytest.mark.asyncio
async def test_reserved_and_on_demand_scale_differently_across_durations(client, auth_headers):
    arch_id, coll_id = await _create_collection(client, auth_headers)

    await client.post(
        f"/api/v1/collections/{coll_id}/sku-selections",
        json={
            "service_code": SERVICE_CODE,
            "sku": ON_DEMAND_SKU,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "10",
        },
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/collections/{coll_id}/sku-selections",
        json={
            "service_code": SERVICE_CODE,
            "sku": RESERVED_SKU,
            "pricing_term": "reserved_1yr",
            "purchase_option": "partial_upfront",
            "usage_quantity": "1",
        },
        headers=auth_headers,
    )

    totals = {}
    for duration in ("1_day", "1_month", "1_year"):
        resp = await client.post(
            f"/api/v1/architectures/{arch_id}/calculate?duration={duration}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["duration"] == duration
        totals[duration] = Decimal(body["total_price"])

    # Both services must be priceable (real SKUs with real rates for these terms).
    assert totals["1_day"] > 0
    # The total strictly grows as the duration widens — on-demand scales up directly, and
    # (006) the reserved portion does too: both its recurring contribution (rate * 24 *
    # duration_days) and its upfront-amortized share (upfront_fee * duration_days / term_days)
    # are linear in duration_days.
    assert totals["1_day"] < totals["1_month"] < totals["1_year"]


@pytest.mark.asyncio
async def test_reserved_1yr_cost_scales_linearly_with_duration_days(client, auth_headers):
    """006: a Reserved-1yr selection's total cost — recurring contribution plus any
    upfront-amortized share — is linear in the requested duration's day-count (both
    components are individually linear in `duration_days`, per FR-001/FR-002), so the 1-day
    cost scaled by 365 equals the 1-year cost exactly. (This no longer relies on any
    duration_days/term_days == 1 special case — it holds for any duration.)"""
    arch_id, coll_id = await _create_collection(client, auth_headers)
    add_resp = await client.post(
        f"/api/v1/collections/{coll_id}/sku-selections",
        json={
            "service_code": SERVICE_CODE,
            "sku": RESERVED_SKU,
            "pricing_term": "reserved_1yr",
            "purchase_option": "partial_upfront",
            "usage_quantity": "2",
        },
        headers=auth_headers,
    )
    assert add_resp.status_code == 201

    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/calculate?duration=1_year", headers=auth_headers
    )
    body = resp.json()
    assert body["line_items"][0]["priceable"] is True
    displayed_cost = Decimal(body["line_items"][0]["price"])
    assert displayed_cost > 0

    resp_day = await client.post(
        f"/api/v1/architectures/{arch_id}/calculate?duration=1_day", headers=auth_headers
    )
    day_cost = Decimal(resp_day.json()["line_items"][0]["price"])
    # Rounded to cents: the 1-day figure is itself the result of a Decimal division by 365
    # (the upfront-amortized share, FR-002) that doesn't terminate exactly, so re-multiplying
    # by 365 and comparing at full Decimal precision would fail on an artifact of that
    # division's rounding, not a real discrepancy — cents is the precision that actually
    # matters for a displayed price.
    assert (day_cost * 365).quantize(Decimal("0.01")) == displayed_cost.quantize(Decimal("0.01"))


# --- 006-fix-reserved-pricing: exact-dollar-figure regression tests (quickstart.md 1-3) ---


@pytest.mark.asyncio
async def test_reserved_no_upfront_matches_bug_report_figures(client, auth_headers):
    """quickstart.md Scenario 1: the exact SKU/term from the bug report, at 1 day / 1 month /
    1 year, matches the precisely-computed expected figures — not the pre-fix $10.962."""
    arch_id, coll_id = await _create_collection(client, auth_headers)
    add_resp = await client.post(
        f"/api/v1/collections/{coll_id}/sku-selections",
        json={
            "service_code": SERVICE_CODE,
            "sku": BUG_REPORT_SKU,
            "pricing_term": "reserved_1yr",
            "purchase_option": "no_upfront",
            "usage_quantity": "1",
        },
        headers=auth_headers,
    )
    assert add_resp.status_code == 201

    expected = {
        "1_day": Decimal("309.77"),
        "1_month": Decimal("9602.76"),
        "1_year": Decimal("113064.71"),
    }
    for duration, expected_cost in expected.items():
        resp = await client.post(
            f"/api/v1/architectures/{arch_id}/calculate?duration={duration}", headers=auth_headers
        )
        body = resp.json()
        assert body["line_items"][0]["priceable"] is True
        cost = Decimal(body["line_items"][0]["price"]).quantize(Decimal("0.01"))
        assert cost == expected_cost, f"duration={duration}"


@pytest.mark.asyncio
async def test_reserved_partial_upfront_matches_bug_report_figures(client, auth_headers):
    """quickstart.md Scenario 2: Partial Upfront's total includes both the recurring and
    upfront-amortized contributions."""
    arch_id, coll_id = await _create_collection(client, auth_headers)
    add_resp = await client.post(
        f"/api/v1/collections/{coll_id}/sku-selections",
        json={
            "service_code": SERVICE_CODE,
            "sku": BUG_REPORT_SKU,
            "pricing_term": "reserved_1yr",
            "purchase_option": "partial_upfront",
            "usage_quantity": "1",
        },
        headers=auth_headers,
    )
    assert add_resp.status_code == 201

    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/calculate?duration=1_month", headers=auth_headers
    )
    body = resp.json()
    assert body["line_items"][0]["priceable"] is True
    cost = Decimal(body["line_items"][0]["price"]).quantize(Decimal("0.01"))
    assert cost == Decimal("9912.50")


@pytest.mark.asyncio
async def test_reserved_all_upfront_never_zero(client, auth_headers):
    """quickstart.md Scenario 3: an All-Upfront selection's $0/hr recurring rate must not
    zero out the total."""
    arch_id, coll_id = await _create_collection(client, auth_headers)
    add_resp = await client.post(
        f"/api/v1/collections/{coll_id}/sku-selections",
        json={
            "service_code": SERVICE_CODE,
            "sku": BUG_REPORT_SKU,
            "pricing_term": "reserved_1yr",
            "purchase_option": "all_upfront",
            "usage_quantity": "1",
        },
        headers=auth_headers,
    )
    assert add_resp.status_code == 201

    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/calculate?duration=1_month", headers=auth_headers
    )
    body = resp.json()
    assert body["line_items"][0]["priceable"] is True
    cost = Decimal(body["line_items"][0]["price"]).quantize(Decimal("0.01"))
    assert cost == Decimal("9762.54")
    assert cost != Decimal("0")
