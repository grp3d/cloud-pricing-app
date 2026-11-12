"""Unit tests for the Azure standard-architecture meter finder (022 research R3, R4).

Runs against a tiny synthetic `price_item` dataset in the pipeline's Azure table shape, written
to `tmp_path`: test input only, never shipped.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from scripts.standard_architectures.resolver import (
    ProviderRule,
    UnrecognizedUnitError,
    resolve,
)

SNAPSHOT = "2026-11-02"

ITEM = (
    "location VARCHAR, service_family VARCHAR, service_name VARCHAR, service_id VARCHAR, "
    "product_name VARCHAR, sku_id VARCHAR, sku_name VARCHAR, arm_sku_name VARCHAR, "
    "meter_id VARCHAR, meter_name VARCHAR, price_type VARCHAR, unit_of_measure VARCHAR, "
    "tier_minimum_units DOUBLE, unit_price DOUBLE"
)

VM = ("Compute", "Virtual Machines", "SVC-VM", "Virtual Machines Dsv5 Series")


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    rows = {
        "eastus": [
            # Two meters for the size: "DZH/0002" sorts after "DZH/0001", which must win.
            ("eastus", *VM, "DZH/0002", "D4s v5", "Standard_D4s_v5", "m-b", "D4s v5", "Consumption", "1 Hour", 0, 0.192),
            ("eastus", *VM, "DZH/0001", "D4s v5", "Standard_D4s_v5", "m-a", "D4s v5", "Consumption", "1 Hour", 0, 0.192),
            # Windows and Reservation rows of the same size: never the chosen meter.
            ("eastus", "Compute", "Virtual Machines", "SVC-VM", "Virtual Machines Dsv5 Series Windows", "DZH/0000", "D4s v5", "Standard_D4s_v5", "m-w", "D4s v5", "Consumption", "1 Hour", 0, 0.376),
            ("eastus", *VM, "DZH/000A", "D4s v5", "Standard_D4s_v5", "m-r", "D4s v5", "Reservation", "1 Hour", 0, 1000.0),
            # Tiered storage.
            ("eastus", "Storage", "Storage", "SVC-ST", "General Block Blob v2", "BLOB/1", "Hot LRS", "Hot_LRS", "m-s", "Hot LRS Data Stored", "Consumption", "1 GB/Month", 0, 0.0208),
            ("eastus", "Storage", "Storage", "SVC-ST", "General Block Blob v2", "BLOB/1", "Hot LRS", "Hot_LRS", "m-s", "Hot LRS Data Stored", "Consumption", "1 GB/Month", 51200, 0.02),
            # A unit the engine doesn't recognize.
            ("eastus", "Other", "Odd", "SVC-ODD", "Odd", "ODD/1", "Odd", "", "m-o", "Odd", "Consumption", "1 Widget", 0, 1.0),
        ],
        "global": [
            ("global", "Networking", "Azure DNS", "SVC-DNS", "Azure DNS", "DNS/1", "Public", "", "m-d", "Public Queries", "Consumption", "1M", 0, 0.4),
        ],
    }
    for location, data in rows.items():
        target = tmp_path / "price_item" / f"region={location}"
        target.mkdir(parents=True)
        con = duckdb.connect()
        con.execute(f"CREATE TABLE t ({ITEM})")
        con.executemany(f"INSERT INTO t VALUES ({','.join('?' for _ in data[0])})", data)
        con.execute(f"COPY t TO '{target / 'part-0.parquet'}' (FORMAT PARQUET)")
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
        "region": "eastus",
        "filters": {
            "service_name": "Virtual Machines",
            "product_name": "Virtual Machines Dsv5 Series",
            "arm_sku_name": "Standard_D4s_v5",
        },
        "expected_unit": "1 Hour",
        "quantity": Decimal("96.0000"),
    }
    base.update(overrides)
    return ProviderRule(**base)


def _resolve(dataset: Path, rules):
    return resolve(rules, files=_files(dataset), snapshot_date=SNAPSHOT, provider="azure")


def test_lowest_item_wins_among_consumption_meters(dataset):
    match = _resolve(dataset, [_rule()]).matches[0]
    assert (match.service_code, match.sku, match.unit) == ("SVC-VM", "DZH/0001/m-a", "1 Hour")


def test_vm_rule_carries_azure_vm_options(dataset):
    match = _resolve(dataset, [_rule(azure_os="linux")]).matches[0]
    assert match.provider_options == {"kind": "azure_vm", "version": 1, "os": "linux"}


def test_global_location_is_searched_with_the_region(dataset):
    rule = _rule(filters={"service_name": "Azure DNS", "meter_name": "Public Queries"}, expected_unit="1M")
    assert _resolve(dataset, [rule]).matches[0].sku == "DNS/1/m-d"


def test_tiered_meter_is_flagged(dataset):
    rule = _rule(
        filters={"product_name": "General Block Blob v2", "meter_name": "Hot LRS Data Stored"},
        expected_unit="1 GB/Month",
    )
    assert _resolve(dataset, [rule]).matches[0].tiered is True


def test_pattern_filter(dataset):
    rule = _rule(filters={"service_name": "Virtual Machines"}, patterns={"product_name": ".* Windows"})
    assert _resolve(dataset, [rule]).matches[0].sku == "DZH/0000/m-w"


def test_no_match_is_an_omission(dataset):
    resolution = _resolve(dataset, [_rule(region="westus2")])
    assert resolution.matches == []
    assert "no matching" in resolution.omissions[0].reason


def test_unrecognized_unit_fails_the_run(dataset):
    rule = _rule(filters={"service_name": "Odd"}, expected_unit=None)
    with pytest.raises(UnrecognizedUnitError):
        _resolve(dataset, [rule])


def test_unknown_filter_column_is_rejected(dataset):
    with pytest.raises(ValueError):
        _resolve(dataset, [_rule(filters={"unit_price": "1"})])
