"""Unit tests for the standard-architecture report layout (022 contracts/generator.md, FR-011).

GCP and Azure reports name the AWS component each row stands in for and the original and chosen
sizes; the AWS report keeps its 014 layout.
"""

from __future__ import annotations

from decimal import Decimal

from scripts.standard_architectures.match_rules import MatchRule
from scripts.standard_architectures.resolver import (
    Match,
    Omission,
    ProviderRule,
    Resolution,
    render_report,
)

SOURCE = {"architectures": [{"id": "arch_a", "name": "Design A", "regions": ["us-east-1"]}]}


def _gcp_resolution() -> Resolution:
    sized = ProviderRule(
        architecture_id="arch_a",
        component_id="ec2_app_primary",
        figure="runningHoursPerMonth",
        region="us-east1",
        quantity=Decimal("96.0000"),
        size_note="t4g.xlarge 4/16 → e2-standard-4 4/16",
    )
    left_out = ProviderRule(
        architecture_id="arch_a",
        component_id="cloudfront_cdn",
        figure="dataTransferOutGB",
        region="us-east1",
        omit_reason="left out to match the AWS version",
    )
    return Resolution(
        snapshot_date="2026-11-02",
        matches=[Match(rule=sized, service_code="SVC-CE", sku="A-CORE", unit="h", tiered=False)],
        omissions=[Omission(rule=left_out, reason=left_out.omit_reason)],
    )


def test_provider_report_names_provider_and_snapshot():
    report = render_report(_gcp_resolution(), SOURCE, provider="gcp")
    assert "Provider: `gcp`" in report
    assert "Pricing snapshot: `2026-11-02`" in report
    assert "## Design A" in report


def test_provider_report_has_aws_component_and_size_columns():
    report = render_report(_gcp_resolution(), SOURCE, provider="gcp")
    assert (
        "| AWS component | Figure | Region | Service | SKU | Unit | Quantity | Tiered | Size | Note |"
        in report
    )
    assert (
        "| ec2_app_primary | runningHoursPerMonth | us-east1 | SVC-CE | A-CORE | h | 96.0000 |  | "
        "t4g.xlarge 4/16 → e2-standard-4 4/16 |  |" in report
    )


def test_provider_report_left_out_table_names_the_aws_component():
    report = render_report(_gcp_resolution(), SOURCE, provider="gcp")
    assert "| AWS component | Figure | Reason |" in report
    assert "| cloudfront_cdn | dataTransferOutGB | left out to match the AWS version |" in report


def test_aws_report_keeps_its_layout():
    rule = MatchRule("arch_a", "ec2", "hours", "us-east-1", ("AmazonEC2",), quantity=Decimal("24.0000"))
    resolution = Resolution(
        snapshot_date="2026-09-24",
        matches=[Match(rule=rule, service_code="AmazonEC2", sku="AAA", unit="Hrs", tiered=False)],
        omissions=[],
    )
    report = render_report(resolution, SOURCE)
    assert "| Component | Figure | Region | Service | SKU | Unit | Quantity | Tiered | Note |" in report
    assert "Provider:" not in report
    assert "AWS component" not in report
