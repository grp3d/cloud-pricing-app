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
