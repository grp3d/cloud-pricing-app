"""Pricing through manifests, end to end against real fixture data (018-app-cloud-deployment,
FR-001–FR-004, FR-059; Story 1). Constitution V: DuckDB query logic, test-first.

The query modules read exactly the files the active snapshot's manifest lists — never a folder
glob — so a folder holding files from two revisions never double-counts, and an extra listed
file is read.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import duckdb
import pytest

from src.pricing_data import active_snapshot
from src.pricing_data.catalog import search_catalog
from src.pricing_data.pricing import lookup_price
from src.pricing_data.regions import list_available_regions

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pricing_parquet"
DATE = "2026-09-24"
KNOWN_SKU = "NN4EGUUQRWVYP98C"  # t3.medium Linux on-demand, us-east-1
REGION_DIR = f"aws/parquet/price_fact/snapshot_date={DATE}/region=us-east-1"


@pytest.fixture
def root(tmp_path, use_pricing_root):
    """A copy of the fixture root, active through PRICING_DATA_URI=file://…"""
    copy = tmp_path / "pipeline"
    shutil.copytree(FIXTURE, copy)
    return copy


def _manifest_path(root: Path) -> Path:
    return root / "aws" / "manifests" / DATE / "manifest.json"


def _write_variant(root: Path, name: str, new_sku: str) -> dict:
    """A price_fact file holding the known SKU's rows under another SKU code."""
    listed = json.loads(_manifest_path(root).read_text())
    source = root / listed["tables"]["price_fact"]["regions"]["us-east-1"]["files"][0]["path"]
    dest = root / REGION_DIR / name
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT * REPLACE ('{new_sku}' AS sku) FROM read_parquet(?) WHERE sku = ?) "
        f"TO '{dest}' (FORMAT parquet)",
        [str(source), KNOWN_SKU],
    )
    rows = con.execute("SELECT count(*) FROM read_parquet(?)", [str(dest)]).fetchone()[0]
    data = dest.read_bytes()
    return {"path": f"{REGION_DIR}/{name}", "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "row_count": rows}


def test_prices_catalog_and_regions_come_from_the_manifest(root, use_pricing_root):
    use_pricing_root(root)
    price = lookup_price(sku=KNOWN_SKU, pricing_term="on_demand",
                         purchase_option="not_applicable", region="us-east-1")
    assert price is not None and price > 0
    results, snapshot, total = search_catalog(text=KNOWN_SKU, limit=10, region="us-east-1")
    assert total >= 1 and KNOWN_SKU in {r["sku"] for r in results}
    assert (snapshot.snapshot_date, snapshot.revision) == (DATE, 1)
    assert "us-east-1" in list_available_regions()


def test_a_second_listed_file_in_a_region_is_read(root, use_pricing_root):
    extra = _write_variant(root, "part-20260924T000000Z-f1a7e0-1.parquet", "TESTSKU0000001")
    manifest = json.loads(_manifest_path(root).read_text())
    manifest["tables"]["price_fact"]["regions"]["us-east-1"]["files"].append(extra)
    _manifest_path(root).write_text(json.dumps(manifest))
    use_pricing_root(root)

    assert lookup_price(sku="TESTSKU0000001", pricing_term="on_demand",
                        purchase_option="not_applicable", region="us-east-1") is not None
    assert lookup_price(sku=KNOWN_SKU, pricing_term="on_demand",
                        purchase_option="not_applicable", region="us-east-1") is not None


def test_an_unlisted_file_in_the_same_folder_is_never_read(root, use_pricing_root):
    _write_variant(root, "part-20260924T000000Z-f1a7e0-2.parquet", "TESTSKU0000002")
    use_pricing_root(root)
    assert lookup_price(sku="TESTSKU0000002", pricing_term="on_demand",
                        purchase_option="not_applicable", region="us-east-1") is None


def test_a_region_with_no_files_is_the_existing_unavailable_error(root, use_pricing_root):
    from src.pricing_data.errors import PricingDataUnavailableError

    use_pricing_root(root)
    with pytest.raises(PricingDataUnavailableError):
        lookup_price(sku=KNOWN_SKU, pricing_term="on_demand",
                     purchase_option="not_applicable", region="sa-east-1")


def test_a_corrected_revision_is_labelled_with_its_revision(root, use_pricing_root):
    """FR-059: a price from a corrected revision never shares its label with the old one."""
    use_pricing_root(root)
    assert active_snapshot.get_active_snapshot().revision == 1

    manifest = json.loads(_manifest_path(root).read_text())
    manifest["revision"], manifest["previous_revision"] = 2, 1
    _manifest_path(root).write_text(json.dumps(manifest))
    latest = root / "aws/manifests/latest.json"
    pointer = json.loads(latest.read_text())
    pointer["revision"] = 2
    latest.write_text(json.dumps(pointer))
    active_snapshot.run_check()

    _results, snapshot, _total = search_catalog(text=KNOWN_SKU, limit=10, region="us-east-1")
    assert (snapshot.snapshot_date, snapshot.revision) == (DATE, 2)
