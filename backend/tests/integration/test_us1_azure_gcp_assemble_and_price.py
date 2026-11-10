"""US1 Independent Test end to end through the API (019, T037, SC-002): an Azure architecture in
`eastus` (D4s v5 Linux, a P10 LRS disk, egress) and a GCP one in `us-east1` (n2-standard-4,
Balanced PD, egress) are assembled, read back and calculated; every line matches the fixture
README's published prices."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.helpers.providers import AZURE, GCP, INDEPENDENT_TEST, build_architecture


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["azure", "gcp"])
async def test_assemble_and_price(client, auth_headers, provider):
    arch_id = await build_architecture(client, auth_headers, provider)
    items = AZURE if provider == "azure" else GCP
    spec = INDEPENDENT_TEST[provider]

    detail = (await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)).json()
    assert detail["provider"] == provider
    (collection,) = detail["collections"]
    assert collection["region"] == spec["region"]
    stored = {s["sku"]: s for s in collection["sku_selections"]}
    for key, _qty, options, _cost in spec["lines"]:
        selection = stored[items[key][1]]
        assert selection["unit"], selection  # resolved through the provider's adapter
        assert selection["provider_options"] == options

    for duration, days in (("1_day", 1), ("1_month", 31), ("1_year", 365)):
        body = (await client.post(f"/api/v1/architectures/{arch_id}/calculate",
                                  params={"duration": duration}, headers=auth_headers)).json()
        assert body["unpriceable"] == []
        by_sku = {line["sku"]: Decimal(line["price"]) for line in body["line_items"]}
        for key, _qty, _opts, month_cost in spec["lines"]:
            assert by_sku[items[key][1]] == pytest.approx(month_cost * days / 31,
                                                          abs=Decimal("1e-9")), (key, duration)
        assert Decimal(body["total_price"]) == pytest.approx(
            sum(c for *_x, c in spec["lines"]) * days / 31, abs=Decimal("1e-9"))
