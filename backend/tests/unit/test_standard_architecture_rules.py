"""Unit tests for the standard-architecture resolver (014-architecture-templates-import-export,
research.md §3-§5).

Quantity formulas are pure. Resolver behavior runs against a tiny synthetic pricing dataset
written to `tmp_path` in the real dataset's partition layout — test input only, never shown to a
user or shipped (the real match rules are exercised against the real/fixture data by
tests/integration/test_standard_architecture_seed.py).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from scripts.standard_architectures.match_rules import (
    MatchRule,
    always_on,
    as_stored,
    daily_dpu,
    fargate_gb,
    fargate_vcpu,
    kinesis_put_payload_units,
    lambda_gb_seconds,
    monthly,
    per_hour_rate,
)
from scripts.standard_architectures.resolver import (
    UnrecognizedUnitError,
    render_report,
    resolve,
    to_export_file,
)

SNAPSHOT = "2026-09-24"


# --- Quantity formulas (research.md §5) ----------------------------------------------------


def test_always_on_is_24_hours_per_unit_per_day():
    assert always_on(4) == Decimal("96.0000")


def test_per_hour_rate_is_24_per_day():
    assert per_hour_rate(2) == Decimal("48.0000")


def test_monthly_divides_by_31_day_month():
    assert monthly(10_000_000) == Decimal("322580.6452")


def test_daily_dpu():
    assert daily_dpu(10, 2) == Decimal("20.0000")


def test_lambda_gb_seconds_per_day():
    assert lambda_gb_seconds(15_000_000, 250, 1024) == Decimal("120967.7419")


def test_fargate_vcpu_and_memory_hours_per_day():
    assert fargate_vcpu(10, 1) == Decimal("240.0000")
    assert fargate_gb(10, 2) == Decimal("480.0000")


def test_kinesis_put_payload_units_per_day():
    """One PUT payload unit is a 25 KB chunk: 500,000 MB/month -> 20,480,000 units/month."""
    assert kinesis_put_payload_units(500_000) == Decimal("660645.1613")


def test_as_stored_is_unconverted():
    assert as_stored(2000) == Decimal("2000.0000")


# --- Resolver against a synthetic dataset --------------------------------------------------


def _write(parquet_dir: Path, table: str, region: str, columns: str, rows: list[tuple]) -> None:
    target = parquet_dir / table / f"snapshot_date={SNAPSHOT}" / f"region={region}"
    target.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"CREATE TABLE t ({columns})")
    if rows:
        placeholders = ",".join("?" for _ in rows[0])
        con.executemany(f"INSERT INTO t VALUES ({placeholders})", rows)
    con.execute(f"COPY t TO '{target / 'part-0.parquet'}' (FORMAT PARQUET)")


PRODUCT_COLUMNS = (
    "sku VARCHAR, service_code VARCHAR, region_code VARCHAR, product_family VARCHAR, "
    "attributes_json VARCHAR"
)
PRICE_COLUMNS = "sku VARCHAR, term VARCHAR, unit VARCHAR, price DOUBLE, begin_range VARCHAR"


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    def attrs(**kv) -> str:
        return json.dumps(kv)

    _write(
        tmp_path,
        "product_dim",
        "us-east-1",
        PRODUCT_COLUMNS,
        [
            # Two exact matches — "BBB" sorts after "AAA", so "AAA" must win.
            ("BBB", "AmazonEC2", "us-east-1", "Compute Instance", attrs(usagetype="BoxUsage:x")),
            ("AAA", "AmazonEC2", "us-east-1", "Compute Instance", attrs(usagetype="BoxUsage:x")),
            # us-east-1 ALB exists only under AmazonEC2 (research.md §4).
            ("ALB1", "AmazonEC2", "us-east-1", "Load Balancer-Application",
             attrs(usagetype="LoadBalancerUsage")),
            # Near-miss vs. exact transfer type.
            ("ACC1", "AWSDataTransfer", "us-east-1", "Data Transfer",
             attrs(transferType="Accelerated InterRegion Outbound", fromRegionCode="us-east-1")),
            ("XFR1", "AWSDataTransfer", "us-east-1", "Data Transfer",
             attrs(transferType="InterRegion Outbound", fromRegionCode="us-east-1")),
            # Tiered SKU (two OnDemand price rows).
            ("TIER", "AmazonS3", "us-east-1", "Storage", attrs(usagetype="TimedStorage-ByteHrs")),
            # A SKU billed in a unit the pricing engine doesn't recognize.
            ("ODD1", "AmazonS3", "us-east-1", "Fee", attrs(usagetype="Weird")),
            # Same attributes but another region's row inside this partition — must not match.
            ("OTHR", "AmazonEC2", "us-west-2", "Compute Instance", attrs(usagetype="BoxUsage:y")),
        ],
    )
    _write(
        tmp_path,
        "price_fact",
        "us-east-1",
        PRICE_COLUMNS,
        [
            ("AAA", "OnDemand", "Hrs", 0.1, "0"),
            ("BBB", "OnDemand", "Hrs", 0.1, "0"),
            ("ALB1", "OnDemand", "Hrs", 0.0225, "0"),
            ("ACC1", "OnDemand", "GB", 0.04, "0"),
            ("XFR1", "OnDemand", "GB", 0.02, "0"),
            ("TIER", "OnDemand", "GB-Mo", 0.023, "0"),
            ("TIER", "OnDemand", "GB-Mo", 0.022, "51200"),
            ("ODD1", "OnDemand", "Widgets", 1.0, "0"),
            ("OTHR", "OnDemand", "Hrs", 0.2, "0"),
        ],
    )
    return tmp_path


def _rule(**overrides) -> MatchRule:
    base = dict(
        architecture_id="arch_a",
        component_id="comp",
        figure="figure",
        region="us-east-1",
        service_codes=("AmazonEC2",),
        product_family="Compute Instance",
        attribute_filters={"usagetype": "BoxUsage:x"},
        expected_unit="Hrs",
        quantity=Decimal("24.0000"),
    )
    base.update(overrides)
    return MatchRule(**base)


def _resolve(dataset: Path, rules):
    return resolve(rules, parquet_dir=dataset, snapshot_date=SNAPSHOT)


def test_first_match_is_lowest_sku(dataset):
    resolution = _resolve(dataset, [_rule()])
    assert [m.sku for m in resolution.matches] == ["AAA"]
    assert resolution.matches[0].unit == "Hrs"


def test_candidate_service_codes_tried_in_order(dataset):
    rule = _rule(
        service_codes=("AWSELB", "AmazonEC2"),
        product_family="Load Balancer-Application",
        attribute_filters={"usagetype": "LoadBalancerUsage"},
    )
    match = _resolve(dataset, [rule]).matches[0]
    assert (match.service_code, match.sku) == ("AmazonEC2", "ALB1")


def test_exact_filters_exclude_near_misses(dataset):
    rule = _rule(
        service_codes=("AWSDataTransfer",),
        product_family="Data Transfer",
        attribute_filters={"transferType": "InterRegion Outbound"},
        expected_unit="GB",
    )
    assert [m.sku for m in _resolve(dataset, [rule]).matches] == ["XFR1"]


def test_rows_for_other_regions_in_the_partition_never_match(dataset):
    rule = _rule(attribute_filters={"usagetype": "BoxUsage:y"})
    resolution = _resolve(dataset, [rule])
    assert resolution.matches == []
    assert "no matching SKU" in resolution.omissions[0].reason


def test_no_match_becomes_logged_omission(dataset):
    rule = _rule(attribute_filters={"usagetype": "does-not-exist"})
    resolution = _resolve(dataset, [rule])
    assert resolution.matches == []
    assert len(resolution.omissions) == 1
    assert resolution.omissions[0].rule is rule


def test_explicit_omit_rule_skips_query(dataset, monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("an omit rule must not query the dataset")

    monkeypatch.setattr("scripts.standard_architectures.resolver.duckdb.connect", _boom)
    rule = _rule(omit_reason="No pricing records for AWS App Mesh")
    resolution = _resolve(dataset, [rule])
    assert resolution.omissions[0].reason == "No pricing records for AWS App Mesh"


def test_unrecognized_unit_fails_loudly(dataset):
    rule = _rule(
        service_codes=("AmazonS3",),
        product_family="Fee",
        attribute_filters={"usagetype": "Weird"},
        expected_unit=None,
    )
    with pytest.raises(UnrecognizedUnitError):
        _resolve(dataset, [rule])


def test_tiered_sku_is_flagged(dataset):
    rule = _rule(
        service_codes=("AmazonS3",),
        product_family="Storage",
        attribute_filters={"usagetype": "TimedStorage-ByteHrs"},
        expected_unit="GB-Mo",
    )
    assert _resolve(dataset, [rule]).matches[0].tiered is True
    assert _resolve(dataset, [_rule()]).matches[0].tiered is False


SOURCE = {
    "architectures": [
        {"id": "arch_a", "name": "Arch A", "regions": ["us-east-1", "us-west-2"]},
    ]
}


def test_export_file_has_one_vpc_per_region_in_source_order(dataset):
    resolution = _resolve(dataset, [_rule()])
    export = to_export_file(resolution, SOURCE)
    [arch] = export.architectures
    assert arch.name == "Arch A"
    assert [(c.ref, c.name, c.region, c.type.value) for c in arch.collections] == [
        ("c1", "VPC (us-east-1)", "us-east-1", "vpc"),
        ("c2", "VPC (us-west-2)", "us-west-2", "vpc"),
    ]
    assert arch.connectors == []
    [selection] = arch.collections[0].sku_selections
    assert (selection.service_code, selection.sku, selection.usage_quantity) == (
        "AmazonEC2",
        "AAA",
        Decimal("24.0000"),
    )
    assert selection.pricing_term.value == "on_demand"
    assert selection.purchase_option.value == "not_applicable"
    assert export.source_username == "Admin"


def test_output_is_deterministic(dataset):
    rules = [_rule(), _rule(figure="other", omit_reason="left out")]
    first = _resolve(dataset, rules)
    second = _resolve(dataset, rules)
    assert to_export_file(first, SOURCE).model_dump_json() == to_export_file(
        second, SOURCE
    ).model_dump_json()
    assert render_report(first) == render_report(second)
    assert "left out" in render_report(first)
