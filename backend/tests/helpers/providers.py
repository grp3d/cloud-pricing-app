"""Azure and GCP fixture items and an API helper for the 019 US1 tests. Item keys and prices are
the fixture READMEs' (`tests/fixtures/pricing_parquet/{azure,gcp}/README.md`)."""

from __future__ import annotations

from decimal import Decimal

AZURE = {
    "vm": ("DZH313Z7MMC8", "DZH318Z08M9W/004T/db8c0962-f3f8-5b44-99aa-f3c7c1e668c8"),
    "disk_p10": ("DZH317F1HKN0", "DZH318Z0BP04/0035/93a6a529-4f49-47cb-9b1e-db9e5f23263f"),
    "egress_mgn": ("DZH318FHKQ5W", "DZH318Z0BNVX/001D/9995d93a-7d35-4d3f-9c69-7a7fea447ef4"),
}
GCP = {
    "n2_core": ("6F81-5844-456A", "BB77-5FDA-69D9"),
    "n2_ram": ("6F81-5844-456A", "5B01-D157-A097"),
    "balanced_pd": ("6F81-5844-456A", "6AE1-525F-8B80"),
    "egress": ("6F81-5844-456A", "F274-1692-F213"),
}
N2_STANDARD_4 = {"kind": "gcp_machine", "version": 1, "vcpus": 4, "memory_gib": "16",
                 "ram_sku": GCP["n2_ram"][1]}

# The Independent Test architectures (US1): every expected line for a 31-day month.
# Azure: 0.192 × 24 h × 31; one P10 disk for its month; 20 GB a day = 620 GB a month,
#   100 GB at $0 then 520 GB at $0.087.
# GCP: (4 × 0.031611 + 16 × 0.004237) × 24 × 31; 100 GiB-month at $0.1;
#   20 GiB a day = 620 GiB, 1 GiB at $0 then 619 at $0.12.
INDEPENDENT_TEST = {
    "azure": {
        "region": "eastus",
        "lines": [
            ("vm", "24", None, Decimal("142.848")),
            ("disk_p10", "1", None, Decimal("19.71")),
            ("egress_mgn", "20", None, Decimal("45.24")),
        ],
    },
    "gcp": {
        "region": "us-east1",
        "lines": [
            ("n2_core", "24", N2_STANDARD_4, Decimal("144.511584")),
            ("balanced_pd", "100", None, Decimal("10.0")),
            ("egress", "20", None, Decimal("74.28")),
        ],
    },
}


async def build_architecture(client, headers, provider: str, *, name: str = "US1") -> str:
    """The provider's Independent Test architecture through the API; returns its id."""
    spec = INDEPENDENT_TEST[provider]
    items = AZURE if provider == "azure" else GCP
    arch = await client.post("/api/v1/architectures", json={"name": name, "provider": provider},
                             headers=headers)
    assert arch.status_code == 201, arch.text
    arch_id = arch.json()["id"]
    coll = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "App", "region": spec["region"]},
        headers=headers,
    )
    assert coll.status_code == 201, coll.text
    for key, quantity, options, _cost in spec["lines"]:
        service_code, sku = items[key]
        body = {"service_code": service_code, "sku": sku, "pricing_term": "on_demand",
                "purchase_option": "not_applicable", "usage_quantity": quantity}
        if options:
            body["provider_options"] = options
        resp = await client.post(f"/api/v1/collections/{coll.json()['id']}/sku-selections",
                                 json=body, headers=headers)
        assert resp.status_code == 201, resp.text
    return arch_id
