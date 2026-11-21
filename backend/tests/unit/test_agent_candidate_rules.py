"""Candidate rules found against the real catalog (024, research R1–R3; 2026-11-13): products
never offered as matches, searches narrowed per source, and ranking that prefers the plain
product in the target's part of the world."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.agent.matching.candidates import (
    excluded,
    gcp_predefined_shape,
    geography_penalty,
    targeted_searches,
)
from src.agent.matching.profiles import ProductProfile


@pytest.mark.parametrize("label", [
    "Memorystore for Redis Committed Use Discounts - 1 Year",
    "Azure Database for MySQL Compute Reservation · Standard",
    "Virtual Machines Dsv5 Series · Standard_D4s_v5 · D4s v5 Spot",
    "N2 Preemptible Instance Core running in Americas",
    "Cloud SQL for MySQL: Read Replica (free with promotional discount)",
    "Cloud SQL for PostgreSQL: Developer Storage in Oregon",
    "Basv2 Series Cloud Services B2as v2",
    "Azure DNS · Private · Private Queries",
])
def test_terms_spot_licences_and_variants_are_never_offered(label):
    assert excluded(label, {})


def test_plain_products_are_offered_and_aws_variants_arent():
    assert not excluded("Virtual Machines Dsv5 Series · Standard_D4s_v5 · D4s v5", {})
    plain = {"tenancy": "Shared", "preInstalledSw": "NA", "capacitystatus": "Used"}
    assert not excluded("Amazon EC2 · m6i.large", plain)
    for variant in ({**plain, "tenancy": "Dedicated"}, {**plain, "preInstalledSw": "SQL Std"},
                    {**plain, "capacitystatus": "UnusedCapacityReservation"}):
        assert excluded("Amazon EC2 · m6i.large", variant)


def vm(**specs) -> ProductProfile:
    return ProductProfile("vm", "compute", "hour", {"vcpu": 4, "memory_gib": Decimal(16),
                                                    **specs})


def test_searches_are_narrowed_where_a_region_has_thousands_of_rows():
    assert targeted_searches("azure", vm()) == [
        {"kind": "vm", "text": r"Standard_[A-Za-z]+4[a-z]*(_| |$)"}]
    db = ProductProfile("managed_db", "database", "hour", {"engine": "postgresql", "vcpu": 4})
    assert targeted_searches("azure", db) == [{"kind": "managed_db", "text": "PostgreSQL Flex"}]
    assert targeted_searches("aws", vm()) == [
        {"service_code": "AmazonEC2", "product_family": "Compute Instance",
         "text": r'"vcpu": ?"4"'}]
    transfer = ProductProfile("data_transfer", "networking", "gb", {"transfer": "inter_region"})
    assert targeted_searches("gcp", transfer) == [
        {"kind": "data_transfer", "text": "Inter[- ]?Region"}]


def test_the_vm_size_pattern_matches_only_that_vcpu_count():
    import re

    pattern = re.compile(targeted_searches("azure", vm())[0]["text"], re.I)
    assert pattern.search("Standard_D4s_v5")
    assert pattern.search("Standard_B4ms ")
    assert not pattern.search("Standard_D48s_v5")
    assert not pattern.search("Standard_D2s_v5")


def test_products_naming_another_part_of_the_world_rank_later():
    assert geography_penalty("Network Inter Region Data Transfer Out from Delhi", "gcp",
                             "us-east4") > 0
    assert geography_penalty("Network Inter Region Data Transfer Out from Northern Virginia",
                             "gcp", "us-east4") == 0
    assert geography_penalty("Standard Storage", "gcp", "unknown-region") == 0
    # Whole words only: "capacity" doesn't name Asia-Pacific ("apac").
    assert geography_penalty("Application Gateway Standard v2 · Standard Capacity Units",
                             "azure", "eastus") == 0


@pytest.mark.parametrize(("vcpu", "memory", "shape"), [
    (4, Decimal(16), (4, Decimal(16))),
    (2, Decimal("6.38"), (2, Decimal(8))),  # 3.19 GiB per vCPU → the 4 GiB per vCPU ratio
    (3, Decimal(12), (4, Decimal(16))),
    (200, Decimal(800), None),
])
def test_gcp_shapes_are_the_smallest_standard_size_at_least_as_large(vcpu, memory, shape):
    assert gcp_predefined_shape(vcpu, memory) == shape


async def test_only_a_transfer_price_for_the_destination_qualifies():
    # Found in the 026 walk-through: us-east-1 → us-west-2 transfer was offered GCP prices to
    # Columbus, Berlin, Bangkok and Kuala Lumpur as exact matches.
    from src.agent.matching.book import SourceProduct
    from src.agent.matching.candidates import _candidates_for
    from src.agent.matching.profiles import profile
    from src.pricing_data.providers.base import CatalogItem

    source_item = CatalogItem(provider="aws", service_code="AWSDataTransfer", service_name=None,
                              product_family="Data Transfer", sku="AWS", summary="",
                              attributes={"usagetype": "USE1-USW2-AWS-Out-Bytes",
                                          "toRegionCode": "us-west-2"}, unit="GB")
    source = SourceProduct(provider="aws", region="us-east-1", service_code="AWSDataTransfer",
                           sku="AWS", label="transfer", where=None,
                           usage_quantity=Decimal(8), unit="GB", pricing_term="on_demand",
                           purchase_option="not_applicable",
                           profile=profile(source_item, unit="GB"), ref="S1")
    rows = [CatalogItem(provider="gcp", service_code="NET", service_name="Networking",
                        product_family="Network", sku=f"SKU-{place}", attributes={},
                        summary=f"Network Inter Region Data Transfer Out from Virginia to {place}",
                        unit="GiBy", kind="data_transfer")
            for place in ("Columbus", "Berlin", "Americas", "Kuala Lumpur")]
    found = await _candidates_for(source, "gcp", "us-east4", rows, {}, {})
    qualifying = [c.label for c in found if c.quality in ("exact", "close")]
    assert qualifying == ["Network Inter Region Data Transfer Out from Virginia to Americas"]
    assert all(c.quality == "partial" for c in found if c.label not in qualifying)
