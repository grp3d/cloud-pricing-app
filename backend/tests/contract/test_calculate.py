"""Contract test for POST /architectures/{id}/calculate
(spec FR-010, FR-011, FR-012; 004-canvas-pricing-improvements FR-001)."""

import pytest

KNOWN_SKU = "NN4EGUUQRWVYP98C"  # real t3.medium Linux on-demand SKU, ~$0.0416/hr
KNOWN_SERVICE_CODE = "AmazonEC2"


@pytest.mark.asyncio
async def test_calculate_sums_priceable_line_items(client, auth_headers):
    arch = await client.post(
        "/api/v1/architectures", json={"name": "Calc Arch", "provider": "aws"}, headers=auth_headers
    )
    arch_id = arch.json()["id"]
    coll = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "Web", "region": "us-east-1"},
        headers=auth_headers,
    )
    coll_id = coll.json()["id"]
    await client.post(
        f"/api/v1/collections/{coll_id}/sku-selections",
        json={
            "service_code": KNOWN_SERVICE_CODE,
            "sku": KNOWN_SKU,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "730",
        },
        headers=auth_headers,
    )

    resp = await client.post(f"/api/v1/architectures/{arch_id}/calculate", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["snapshot_date"]
    # 018-app-cloud-deployment, FR-059: the revision travels with the date.
    from src.pricing_data.active_snapshot import get_active_snapshot

    active = get_active_snapshot()
    assert (body["snapshot_date"], body["snapshot_revision"]) == (
        active.snapshot_date, active.revision
    )
    assert float(body["total_price"]) > 0
    assert len(body["line_items"]) == 1
    assert body["line_items"][0]["priceable"] is True
    assert body["unpriceable"] == []


@pytest.mark.asyncio
async def test_calculate_flags_unpriceable_sku_without_estimating(client, auth_headers):
    arch = await client.post(
        "/api/v1/architectures",
        json={"name": "Calc Arch 2", "provider": "aws"},
        headers=auth_headers,
    )
    arch_id = arch.json()["id"]
    coll = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "Web", "region": "us-east-1"},
        headers=auth_headers,
    )
    coll_id = coll.json()["id"]
    await client.post(
        f"/api/v1/collections/{coll_id}/sku-selections",
        json={
            "service_code": KNOWN_SERVICE_CODE,
            "sku": "DOES-NOT-EXIST-SKU",
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "1",
        },
        headers=auth_headers,
    )

    resp = await client.post(f"/api/v1/architectures/{arch_id}/calculate", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_price"] == "0"
    assert len(body["unpriceable"]) == 1
    assert body["line_items"][0]["priceable"] is False
    assert body["line_items"][0]["price"] is None
    # 004-canvas-pricing-improvements FR-012: the entry names its containing Collection.
    assert body["unpriceable"][0]["components"] == ["Web"]


@pytest.mark.asyncio
async def test_calculate_defaults_to_one_month_duration(client, auth_headers):
    """004-canvas-pricing-improvements FR-001."""
    arch = await client.post(
        "/api/v1/architectures",
        json={"name": "Duration Default", "provider": "aws"},
        headers=auth_headers,
    )
    arch_id = arch.json()["id"]

    resp = await client.post(f"/api/v1/architectures/{arch_id}/calculate", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["duration"] == "1_month"


@pytest.mark.asyncio
async def test_calculate_accepts_and_echoes_duration_param(client, auth_headers):
    """004-canvas-pricing-improvements FR-001."""
    arch = await client.post(
        "/api/v1/architectures",
        json={"name": "Duration Param", "provider": "aws"},
        headers=auth_headers,
    )
    arch_id = arch.json()["id"]

    for duration in ("1_day", "1_month", "1_year"):
        resp = await client.post(
            f"/api/v1/architectures/{arch_id}/calculate?duration={duration}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["duration"] == duration


# --- 019 (T036, contracts §5, FR-003, FR-007) --------------------------------------------------

from decimal import Decimal  # noqa: E402

from tests.helpers.providers import (  # noqa: E402
    AZURE,
    INDEPENDENT_TEST,
    build_architecture,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["azure", "gcp"])
async def test_other_providers_calculate_from_their_own_snapshot(client, auth_headers, provider):
    arch_id = await build_architecture(client, auth_headers, provider)
    resp = await client.post(f"/api/v1/architectures/{arch_id}/calculate",
                             params={"duration": "1_month"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["snapshot_date"], body["snapshot_revision"]) == ("2026-11-02", 1)
    assert body["unpriceable"] == []
    costs = sorted(Decimal(line["price"]) for line in body["line_items"])
    expected = sorted(c for *_x, c in INDEPENDENT_TEST[provider]["lines"])
    assert costs == pytest.approx(expected, abs=Decimal("1e-9"))
    assert {line["price_type_label"] for line in body["line_items"]} == {"On demand"}
    tiered = [line for line in body["line_items"] if line["tiers"]]
    assert len(tiered) == 1  # the egress line
    assert sum(Decimal(p["cost"]) for p in tiered[0]["tiers"]) == pytest.approx(
        Decimal(tiered[0]["price"]), abs=Decimal("1e-20"))


@pytest.mark.asyncio
async def test_gcp_machine_lines_show_their_components(client, auth_headers):
    arch_id = await build_architecture(client, auth_headers, "gcp")
    body = (await client.post(f"/api/v1/architectures/{arch_id}/calculate",
                              headers=auth_headers)).json()
    (machine,) = [line for line in body["line_items"] if line["components"]]
    vcpus, ram = machine["components"]
    assert (vcpus["label"], Decimal(vcpus["quantity"]), Decimal(vcpus["cost"])) == (
        "vCPUs", Decimal(2976), Decimal("94.074336"))
    assert (ram["label"], Decimal(ram["quantity"]), Decimal(ram["cost"])) == (
        "Memory (GiB)", Decimal(11904), Decimal("50.437248"))
    assert Decimal(vcpus["cost"]) + Decimal(ram["cost"]) == Decimal(machine["price"])


@pytest.mark.asyncio
async def test_azure_reservation_and_unpublished_price(client, auth_headers):
    arch = (await client.post("/api/v1/architectures", json={"name": "R", "provider": "azure"},
                              headers=auth_headers)).json()
    coll = (await client.post(f"/api/v1/architectures/{arch['id']}/collections",
                              json={"type": "application_component", "name": "A",
                                    "region": "eastus"}, headers=auth_headers)).json()
    service_code, sku = AZURE["vm"]
    base = {"service_code": service_code, "sku": sku, "pricing_term": "reserved_1yr",
            "purchase_option": "not_applicable", "usage_quantity": "1"}
    reserved = await client.post(f"/api/v1/collections/{coll['id']}/sku-selections", json=base,
                                 headers=auth_headers)
    # A Windows VM has no reservation in the fixture: stored, but not published.
    windows = await client.post(
        f"/api/v1/collections/{coll['id']}/sku-selections",
        json={**base, "provider_options": {"kind": "azure_vm", "version": 1, "os": "windows"}},
        headers=auth_headers,
    )
    assert reserved.status_code == windows.status_code == 201
    body = (await client.post(f"/api/v1/architectures/{arch['id']}/calculate",
                              params={"duration": "1_year"}, headers=auth_headers)).json()
    (line,) = [li for li in body["line_items"] if li["priceable"]]
    assert Decimal(line["price"]) == Decimal("1038.0")  # the whole term's fee, for 365 days
    assert line["price_type_label"] == "Reserved, 1 year"
    (missing,) = body["unpriceable"]
    assert missing["sku_selection_id"] == windows.json()["id"]
    assert missing["reason"].startswith("not published")
