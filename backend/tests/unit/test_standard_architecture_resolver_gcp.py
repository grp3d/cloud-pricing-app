"""Unit tests for the GCP standard-architecture SKU finder (022 research R3, R4).

Runs against a tiny synthetic dataset in the pipeline's GCP table shapes (`service`, `sku`,
`sku_price`, `sku_price_tier`), written to `tmp_path`: test input only, never shipped. The real
GCP rules are exercised against the fixture data by the integration tests.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from scripts.standard_architectures.resolver import (
    GcpMachine,
    ProviderRule,
    UnrecognizedUnitError,
    resolve,
)

SNAPSHOT = "2026-11-02"


def _write(root: Path, table: str, location: str, columns: str, rows: list[tuple]) -> None:
    target = root / table / f"region={location}"
    target.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"CREATE TABLE t ({columns})")
    if rows:
        con.executemany(f"INSERT INTO t VALUES ({','.join('?' for _ in rows[0])})", rows)
    con.execute(f"COPY t TO '{target / 'part-0.parquet'}' (FORMAT PARQUET)")


SKU = (
    "location VARCHAR, sku_id VARCHAR, service_id VARCHAR, display_name VARCHAR, "
    "product_taxonomy VARCHAR[], geo_taxonomy_type VARCHAR"
)
PRICE = (
    "location VARCHAR, sku_id VARCHAR, consumption_model VARCHAR, "
    "consumption_model_description VARCHAR, unit VARCHAR, unit_quantity DECIMAL(18,6)"
)
TIER = "location VARCHAR, sku_id VARCHAR, consumption_model VARCHAR, start_amount DECIMAL(18,6), list_price DECIMAL(18,9)"


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    _write(tmp_path, "service", "global", "service_id VARCHAR, display_name VARCHAR", [
        ("SVC-CE", "Compute Engine"),
        ("SVC-DNS", "Cloud DNS"),
    ])
    tax = ["GCP", "Compute", "GCE", "VMs On Demand", "Cores: Per Core", "E2"]
    _write(tmp_path, "sku", "us-east1", SKU, [
        # Two matches: "B-CORE" sorts after "A-CORE", so "A-CORE" must win.
        ("us-east1", "B-CORE", "SVC-CE", "E2 Instance Core running in Americas", tax, "TYPE_REGIONAL"),
        ("us-east1", "A-CORE", "SVC-CE", "E2 Instance Core running in Americas", tax, "TYPE_REGIONAL"),
        ("us-east1", "A-RAM", "SVC-CE", "E2 Instance Ram running in Americas", tax, "TYPE_REGIONAL"),
        # Only a commitment price: never matched.
        ("us-east1", "CUD-ONLY", "SVC-CE", "Commitment v1: E2 Cpu", tax, "TYPE_REGIONAL"),
        # Billed in a unit the engine doesn't recognize.
        ("us-east1", "ODD", "SVC-CE", "Odd thing", tax, "TYPE_REGIONAL"),
        # Tiered egress.
        ("us-east1", "EGRESS", "SVC-CE", "Network Internet Egress", ["GCP", "Network"], "TYPE_REGIONAL"),
    ])
    _write(tmp_path, "sku", "global", SKU, [
        ("global", "DNS-Q", "SVC-DNS", "DNS Query (port 53)", ["GCP", "Network", "DNS"], "TYPE_GLOBAL"),
    ])
    _write(tmp_path, "sku_price", "us-east1", PRICE, [
        ("us-east1", "B-CORE", "m1", "Default", "h", 1),
        ("us-east1", "A-CORE", "m1", "Default", "h", 1),
        ("us-east1", "A-RAM", "m1", "Default", "GiBy.h", 1),
        ("us-east1", "CUD-ONLY", "m2", "Compute Engine CUD - 1 Year", "h", 1),
        ("us-east1", "ODD", "m1", "Default", "widgets", 1),
        ("us-east1", "EGRESS", "m1", "Default", "GiBy", 1),
    ])
    _write(tmp_path, "sku_price", "global", PRICE, [
        ("global", "DNS-Q", "m1", "Default", "count", 1000000),
    ])
    _write(tmp_path, "sku_price_tier", "us-east1", TIER, [
        ("us-east1", "A-CORE", "m1", 0, 0.02),
        ("us-east1", "B-CORE", "m1", 0, 0.02),
        ("us-east1", "A-RAM", "m1", 0, 0.003),
        ("us-east1", "ODD", "m1", 0, 1),
        ("us-east1", "EGRESS", "m1", 0, 0.12),
        ("us-east1", "EGRESS", "m1", 1024, 0.11),
    ])
    _write(tmp_path, "sku_price_tier", "global", TIER, [("global", "DNS-Q", "m1", 0, 0.4)])
    return tmp_path


def _files(root: Path):
    def files(table: str, location: str) -> list[str]:
        path = root / table / f"region={location}" / "part-0.parquet"
        return [str(path)] if path.exists() else []

    return files


def _rule(**overrides) -> ProviderRule:
    base = {
        "architecture_id": "arch_a",
        "component_id": "ec2_app",
        "figure": "runningHoursPerMonth",
        "region": "us-east1",
        "filters": {"service_name": "Compute Engine"},
        "patterns": {"display_name": "E2 Instance Core running in .*"},
        "expected_unit": "h",
        "quantity": Decimal("96.0000"),
    }
    base.update(overrides)
    return ProviderRule(**base)


def _resolve(dataset: Path, rules):
    return resolve(rules, files=_files(dataset), snapshot_date=SNAPSHOT, provider="gcp")


def test_lowest_sku_id_wins(dataset):
    match = _resolve(dataset, [_rule()]).matches[0]
    assert (match.service_code, match.sku, match.unit) == ("SVC-CE", "A-CORE", "h")


def test_only_default_consumption_model_counts(dataset):
    rule = _rule(patterns={"display_name": "Commitment v1: E2 Cpu"})
    resolution = _resolve(dataset, [rule])
    assert resolution.matches == []
    assert "no matching SKU" in resolution.omissions[0].reason


def test_global_location_is_searched_with_the_region(dataset):
    rule = _rule(
        filters={"service_name": "Cloud DNS"},
        patterns={"display_name": "DNS Query.*"},
        expected_unit="count",
    )
    match = _resolve(dataset, [rule]).matches[0]
    assert (match.service_code, match.sku) == ("SVC-DNS", "DNS-Q")


def test_expected_unit_filters(dataset):
    assert _resolve(dataset, [_rule(expected_unit="GiBy.h")]).matches == []


def test_tiered_sku_is_flagged(dataset):
    rule = _rule(patterns={"display_name": "Network Internet Egress"}, expected_unit="GiBy")
    assert _resolve(dataset, [rule]).matches[0].tiered is True


def test_unrecognized_unit_fails_the_run(dataset):
    rule = _rule(patterns={"display_name": "Odd thing"}, expected_unit=None)
    with pytest.raises(UnrecognizedUnitError):
        _resolve(dataset, [rule])


def test_omit_reason_skips_the_lookup(dataset):
    resolution = _resolve(dataset, [_rule(omit_reason="left out to match the AWS version")])
    assert resolution.matches == []
    assert resolution.omissions[0].reason == "left out to match the AWS version"


def test_machine_rule_carries_gcp_machine_options_with_the_ram_sku(dataset):
    rule = _rule(
        machine=GcpMachine(
            vcpus=4,
            memory_gib=Decimal("16"),
            ram_patterns={"display_name": "E2 Instance Ram running in .*"},
        )
    )
    match = _resolve(dataset, [rule]).matches[0]
    assert match.sku == "A-CORE"
    assert match.provider_options == {
        "kind": "gcp_machine",
        "version": 1,
        "vcpus": 4,
        "memory_gib": "16",
        "ram_sku": "A-RAM",
    }


def test_machine_without_a_ram_sku_is_left_out(dataset):
    rule = _rule(
        machine=GcpMachine(vcpus=4, memory_gib=Decimal("16"), ram_patterns={"display_name": "nope"})
    )
    resolution = _resolve(dataset, [rule])
    assert resolution.matches == []
    assert "RAM" in resolution.omissions[0].reason


def test_unknown_filter_column_is_rejected(dataset):
    with pytest.raises(ValueError):
        _resolve(dataset, [_rule(filters={"drop table": "x"})])
