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


# --- 020 (T003, contracts/api.md §1): the snapshot carries provider, region and options -------

from tests.helpers.providers import GCP, N2_STANDARD_4  # noqa: E402

AWS_EU_WEST_1_SKU = "22857BA35WWDDHD7"  # fixture EC2 on-demand in eu-west-1, $0.2116/hr
SNAPSHOT_URL = "/api/v1/catalog/calculate-snapshot"


def _snapshot_line(service_code, sku, quantity, *, region=None, options=None):
    line = {"service_code": service_code, "sku": sku, "pricing_term": "on_demand",
            "purchase_option": "not_applicable", "usage_quantity": quantity}
    if region is not None:
        line["region"] = region
    if options is not None:
        line["provider_options"] = options
    return line


async def _snapshot(client, headers, selections, *, provider=None, duration="1_month"):
    body = {"duration": duration, "selections": selections}
    if provider is not None:
        body["provider"] = provider
    return await client.post(SNAPSHOT_URL, json=body, headers=headers)


def _gcp_lines(options=N2_STANDARD_4):
    return [
        _snapshot_line(*GCP["n2_core"], "24", region="us-east1", options=options),
        _snapshot_line(*GCP["balanced_pd"], "100", region="us-east1"),
        _snapshot_line(*GCP["egress"], "20", region="us-east1"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("duration", ["1_month", "1_year"])
async def test_gcp_snapshot_matches_the_architecture_calculation(client, auth_headers, duration):
    arch_id = await build_architecture(client, auth_headers, "gcp")
    calculated = await client.post(f"/api/v1/architectures/{arch_id}/calculate",
                                   params={"duration": duration}, headers=auth_headers)
    resp = await _snapshot(client, auth_headers, _gcp_lines(), provider="gcp", duration=duration)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["unpriceable"] == []
    assert Decimal(body["total_price"]) == Decimal(calculated.json()["total_price"])


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"vcpus": 8}, {"memory_gib": "32"}])
async def test_gcp_snapshot_total_follows_vcpus_and_memory(client, auth_headers, change):
    base = await _snapshot(client, auth_headers, _gcp_lines(), provider="gcp")
    edited = await _snapshot(client, auth_headers, _gcp_lines({**N2_STANDARD_4, **change}),
                             provider="gcp")
    assert edited.status_code == 200, edited.text
    assert Decimal(edited.json()["total_price"]) > Decimal(base.json()["total_price"])


@pytest.mark.asyncio
async def test_azure_snapshot_prices_the_windows_meter(client, auth_headers):
    vm = AZURE["vm"]
    linux = await _snapshot(client, auth_headers, [_snapshot_line(
        *vm, "24", region="eastus", options={"kind": "azure_vm", "version": 1, "os": "linux"})],
        provider="azure")
    windows = await _snapshot(client, auth_headers, [_snapshot_line(
        *vm, "24", region="eastus", options={"kind": "azure_vm", "version": 1, "os": "windows"})],
        provider="azure")
    assert linux.status_code == windows.status_code == 200, windows.text
    # Fixture README: D4s v5 Linux $0.192/h, Windows $0.376/h; 24 h a day for a 31-day month.
    assert Decimal(linux.json()["total_price"]) == Decimal("744") * Decimal("0.192")
    assert Decimal(windows.json()["total_price"]) == Decimal("744") * Decimal("0.376")


@pytest.mark.asyncio
async def test_aws_snapshot_prices_in_the_selection_region(client, auth_headers):
    resp = await _snapshot(client, auth_headers, [_snapshot_line(
        "AmazonEC2", AWS_EU_WEST_1_SKU, "24", region="eu-west-1")], provider="aws")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["unpriceable"] == []
    assert Decimal(body["total_price"]) == pytest.approx(Decimal("744") * Decimal("0.2116"))


@pytest.mark.asyncio
async def test_aws_snapshot_without_provider_or_region_is_unchanged(client, auth_headers):
    """An older client: no `provider`, no `region` → us-east-1, as in v0.0.2."""
    resp = await _snapshot(client, auth_headers, [_snapshot_line(
        KNOWN_SERVICE_CODE, KNOWN_SKU, "24")])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["unpriceable"] == []
    assert Decimal(body["total_price"]) == pytest.approx(Decimal("744") * Decimal("0.0416"))
    # And the eu-west-1 SKU isn't found there, which is exactly today's behaviour.
    legacy = await _snapshot(client, auth_headers, [_snapshot_line(
        "AmazonEC2", AWS_EU_WEST_1_SKU, "24")])
    assert len(legacy.json()["unpriceable"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "options"),
    [
        ("aws", N2_STANDARD_4),
        ("azure", N2_STANDARD_4),
        ("gcp", {"kind": "azure_vm", "version": 1, "os": "linux"}),
        (None, {"kind": "azure_vm", "version": 1, "os": "linux"}),
    ],
)
async def test_snapshot_options_must_match_the_provider(client, auth_headers, provider, options):
    resp = await _snapshot(client, auth_headers, [_snapshot_line(
        *GCP["n2_core"], "24", region="us-east1", options=options)], provider=provider)
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_empty_snapshot_with_a_provider_is_still_a_400(client, auth_headers):
    resp = await _snapshot(client, auth_headers, [], provider="gcp")
    assert resp.status_code == 400
    assert resp.json()["error"] == "empty_snapshot"
