"""`ActiveSnapshot` per provider (019, T017; research R1, R5): tables, locations and the
`global` files that every location's lookups also read."""

from __future__ import annotations

from pathlib import Path

from src.pricing_data.manifest import Manifest
from src.pricing_data.snapshot import ActiveSnapshot

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "pricing_parquet"


def _snapshot(provider: str) -> ActiveSnapshot:
    path = next((ROOT / provider / "manifests").glob("*/manifest.json"))
    manifest = Manifest.model_validate_json(path.read_text())
    return ActiveSnapshot.from_manifest(manifest, base_dir=ROOT, pinned=False)


def test_tables_are_the_providers_own():
    assert _snapshot("azure").tables == ("price_item", "price_item_savings_plan")
    assert _snapshot("aws").tables[-1] == "price_fact"


def test_locations_come_from_the_manifests_succeeded_regions():
    assert _snapshot("azure").locations() == ["eastus", "global", "north-america"]
    assert _snapshot("gcp").locations() == ["global", "us-east1"]
    assert "us-west-2" in _snapshot("aws").locations()


def test_common_regions_works_for_every_provider():
    assert _snapshot("azure").common_regions() == {"eastus", "global", "north-america"}
    # GCP's `service` table lists every location, with files only in `global`.
    assert _snapshot("gcp").common_regions() == {"global", "us-east1"}


def test_files_with_global_adds_the_global_partition():
    gcp = _snapshot("gcp")
    files = gcp.files_with_global("sku", "us-east1")
    assert any("region=us-east1" in f for f in files)
    assert any("region=global" in f for f in files)
    assert gcp.files_with_global("sku", "global") == gcp.files("sku", "global")
    # AWS has no `global` partition: just the location's own files.
    aws = _snapshot("aws")
    assert aws.files_with_global("price_fact", "us-east-1") == aws.files("price_fact", "us-east-1")
