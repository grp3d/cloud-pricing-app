"""Manifest validation (018-app-cloud-deployment, FR-004, FR-006, FR-007; data-model.md §3).
Constitution V: selection of pricing data is test-first.

`validate_manifest` is pure: a manifest is usable only if its status, versions, file paths and
(through the pointer) date and revision all check out. Any failure rejects the whole manifest
with a reason, before anything is read or fetched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pricing_data.manifest import (
    LatestPointer,
    Manifest,
    RejectedManifest,
    parse_manifest,
    validate_manifest,
)

MANIFESTS = Path(__file__).resolve().parents[1] / "fixtures" / "manifests"
FIXTURE_MANIFEST = (
    Path(__file__).resolve().parents[1]
    / "fixtures/pricing_parquet/aws/manifests/2026-09-24/manifest.json"
)


def _load(name: str) -> Manifest:
    return Manifest.model_validate(json.loads((MANIFESTS / f"{name}.json").read_text()))


def _pointer(date: str = "2026-10-05", revision: int = 1) -> LatestPointer:
    return LatestPointer(
        manifest_version="1.0",
        provider="aws",
        snapshot_date=date,
        revision=revision,
        run_id="20261005T141210Z-9c41e2",
        manifest_path=f"aws/manifests/{date}/manifest.json",
        updated_at="2026-10-05T14:19:03Z",
    )


def test_the_fixture_manifest_is_usable():
    manifest = Manifest.model_validate_json(FIXTURE_MANIFEST.read_text())
    assert validate_manifest(manifest, "aws") is manifest


def test_minor_version_bump_is_accepted():
    manifest = _load("minor_bump_extra_field")
    assert validate_manifest(manifest, "aws") is manifest


@pytest.mark.parametrize("name", ["partial", "failed", "purged"])
def test_non_succeeded_status_is_rejected(name):
    result = validate_manifest(_load(name), "aws")
    assert isinstance(result, RejectedManifest)
    assert name in result.reason
    assert (result.snapshot_date, result.revision) == ("2026-10-05", 1)


@pytest.mark.parametrize(
    "name",
    ["bad_path_dotdot", "bad_path_absolute", "bad_path_other_date", "bad_path_other_region"],
)
def test_any_bad_path_rejects_the_whole_manifest(name):
    result = validate_manifest(_load(name), "aws")
    assert isinstance(result, RejectedManifest)
    assert "path" in result.reason


def test_unsupported_major_version_is_rejected():
    result = validate_manifest(_load("unsupported_major"), "aws")
    assert isinstance(result, RejectedManifest)
    assert "2.0" in result.reason


def test_unsupported_table_schema_version_is_rejected():
    result = validate_manifest(_load("unsupported_schema"), "aws")
    assert isinstance(result, RejectedManifest)
    assert "price_fact" in result.reason and "schema" in result.reason


def test_missing_table_is_rejected():
    manifest = _load("minor_bump_extra_field")
    del manifest.tables["region_dim"]
    result = validate_manifest(manifest, "aws")
    assert isinstance(result, RejectedManifest)
    assert "region_dim" in result.reason


def test_other_provider_is_rejected():
    result = validate_manifest(_load("minor_bump_extra_field"), "gcp")
    assert isinstance(result, RejectedManifest)


def test_pointer_date_mismatch_is_rejected():
    result = validate_manifest(_load("minor_bump_extra_field"), "aws",
                               pointer=_pointer(date="2026-10-06"))
    assert isinstance(result, RejectedManifest)
    assert "date" in result.reason


def test_revision_below_the_pointer_is_rejected():
    result = validate_manifest(_load("minor_bump_extra_field"), "aws", pointer=_pointer(revision=2))
    assert isinstance(result, RejectedManifest)
    assert "revision" in result.reason


def test_revision_above_the_pointer_is_accepted():
    manifest = _load("minor_bump_extra_field")
    manifest.revision = 3
    assert validate_manifest(manifest, "aws", pointer=_pointer(revision=2)) is manifest


@pytest.mark.parametrize("raw", [b"not json", b"{}", b'{"manifest_version": "1.0"}'])
def test_unparseable_documents_are_rejected_not_raised(raw):
    result = parse_manifest(raw, snapshot_date="2026-10-05")
    assert isinstance(result, RejectedManifest)
    assert result.snapshot_date == "2026-10-05"


# --- 019-gcp-azure-providers-trends (research R1): per-provider tables, manifest 1.1 ---------

PRICING_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "pricing_parquet"


def _provider_manifest(provider: str) -> Manifest:
    path = next((PRICING_FIXTURES / provider / "manifests").glob("*/manifest.json"))
    return Manifest.model_validate_json(path.read_text())


def test_provider_table_registry():
    from src.pricing_data.manifest import PROVIDER_TABLES

    assert len(PROVIDER_TABLES["aws"]) == 5
    assert set(PROVIDER_TABLES["azure"]) == {"price_item", "price_item_savings_plan"}
    assert set(PROVIDER_TABLES["gcp"]) == {"service", "sku", "sku_price", "sku_price_tier"}


@pytest.mark.parametrize("provider", ["azure", "gcp"])
def test_azure_and_gcp_fixture_manifests_are_usable(provider):
    # Manifest 1.1: `catalog`, `excluded_price_types` and the wider `run.region_results` are
    # accepted and ignored; `global`, `north-america` locations pass the path check.
    manifest = _provider_manifest(provider)
    assert manifest.manifest_version == "1.1"
    assert validate_manifest(manifest, provider) is manifest


def test_manifest_1_1_optional_fields_are_accepted_and_ignored():
    manifest = _provider_manifest("azure")
    raw = manifest.model_dump()
    raw["excluded_price_types"] = ["DevTestConsumption"]
    raw["catalog"] = {"api_version": "v2beta", "requests_made": 45}
    raw["run"]["region_results"] = [{"region": "eastus", "items_received": 30, "foo": 1}]
    again = Manifest.model_validate(raw)
    assert validate_manifest(again, "azure") is again


def test_a_table_of_another_provider_is_rejected():
    manifest = _provider_manifest("azure")
    manifest.tables["price_fact"] = manifest.tables["price_item"]
    result = validate_manifest(manifest, "azure")
    assert isinstance(result, RejectedManifest)
    assert "price_fact" in result.reason


def test_a_missing_provider_table_is_rejected():
    manifest = _provider_manifest("gcp")
    del manifest.tables["sku_price_tier"]
    result = validate_manifest(manifest, "gcp")
    assert isinstance(result, RejectedManifest)
    assert "sku_price_tier" in result.reason


def test_unsupported_schema_version_for_a_provider_table_is_rejected():
    manifest = _provider_manifest("gcp")
    manifest.tables["sku"].schema_version = 2
    result = validate_manifest(manifest, "gcp")
    assert isinstance(result, RejectedManifest)
    assert "sku" in result.reason and "schema" in result.reason


def test_unknown_provider_is_rejected():
    manifest = _provider_manifest("gcp")
    manifest.provider = "oracle"
    result = validate_manifest(manifest, "oracle")
    assert isinstance(result, RejectedManifest)
    assert "oracle" in result.reason


@pytest.mark.parametrize("location", ["global", "north-america", "northamerica-northeast1"])
def test_location_names_of_every_provider_pass_the_path_check(location):
    manifest = _provider_manifest("gcp")
    entry = manifest.tables["sku"].regions["us-east1"].model_copy(deep=True)
    for data_file in entry.files:
        data_file.path = data_file.path.replace("region=us-east1", f"region={location}")
    manifest.tables["sku"].regions[location] = entry
    assert validate_manifest(manifest, "gcp") is manifest


@pytest.mark.parametrize("location", ["US East", "us_east1", "-us", "us-", ""])
def test_malformed_location_names_are_rejected(location):
    manifest = _provider_manifest("gcp")
    entry = manifest.tables["sku"].regions["us-east1"].model_copy(deep=True)
    for data_file in entry.files:
        data_file.path = data_file.path.replace("region=us-east1", f"region={location}")
    manifest.tables["sku"].regions[location] = entry
    result = validate_manifest(manifest, "gcp")
    assert isinstance(result, RejectedManifest)
    assert "location" in result.reason or "path" in result.reason
