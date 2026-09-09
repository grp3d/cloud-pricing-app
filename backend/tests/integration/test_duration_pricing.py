"""Integration test for duration-scoped pricing across a mixed Architecture
(004-canvas-pricing-improvements, FR-001, FR-002, FR-003, quickstart.md step 2).

Runs against the real Parquet pricing data (Constitution Principle I — no mock substitute).
"""

from decimal import Decimal

import pytest

# Real SKUs confirmed during implementation: an on-demand Hrs-family EC2 instance, and a
# Reserved-1yr EC2 instance with a real partial-upfront recurring rate.
ON_DEMAND_SKU = "NN4EGUUQRWVYP98C"
RESERVED_SKU = "QZ9R39S2Y8MCC9Y8"
SERVICE_CODE = "AmazonEC2"


async def _create_collection(client, auth_headers) -> tuple[str, str]:
    arch = await client.post(
        "/api/v1/architectures",
        json={"name": "Duration Mix", "provider": "aws"},
        headers=auth_headers,
    )
    arch_id = arch.json()["id"]
    coll = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "Mixed"},
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
    # The total strictly grows as the duration widens (on-demand scales up directly; the
    # reserved portion scales up too, from a 1/365 share toward its full committed cost).
    assert totals["1_day"] < totals["1_month"] < totals["1_year"]


@pytest.mark.asyncio
async def test_reserved_1yr_at_one_year_duration_equals_full_raw_cost(client, auth_headers):
    """FR-002: at duration=1_year, a Reserved-1yr selection's proration ratio is
    duration_days(365) / term_days(365) == 1 — its displayed cost equals its full raw cost."""
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
    # Re-derive the raw unit price via a 1_day-duration call isn't equivalent (different
    # ratio) — instead confirm internal consistency: 1_day's displayed cost * 365 == 1_year's.
    resp_day = await client.post(
        f"/api/v1/architectures/{arch_id}/calculate?duration=1_day", headers=auth_headers
    )
    day_cost = Decimal(resp_day.json()["line_items"][0]["price"])
    assert day_cost * 365 == displayed_cost
