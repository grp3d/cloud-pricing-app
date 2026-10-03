"""The app's manifest models accept everything the pipeline's published contract allows
(018-app-cloud-deployment, FR-006; tests/fixtures/contracts/, vendored from the pipeline).

If the pipeline's contract changes, re-copy the schemas (SOURCE.md) and this test shows whether
the app still parses its documents.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from src.pricing_data.manifest import LatestPointer, Manifest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CONTRACTS = FIXTURES / "contracts"
PRICING_ROOT = FIXTURES / "pricing_parquet"


def _schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text())


@pytest.mark.parametrize("example", _schema("latest.schema.json")["examples"])
def test_pointer_model_parses_every_schema_example(example):
    pointer = LatestPointer.model_validate(example)
    assert pointer.snapshot_date == example["snapshot_date"]
    assert pointer.revision == example["revision"]


@pytest.mark.parametrize("example", _schema("manifest.schema.json")["examples"])
def test_manifest_model_parses_every_schema_example(example):
    manifest = Manifest.model_validate(example)
    assert manifest.snapshot_date == example["snapshot_date"]
    assert set(manifest.tables) == set(example["tables"])


def test_fixture_documents_are_valid_against_the_contract_and_the_models():
    checker = jsonschema.FormatChecker()
    latest = json.loads((PRICING_ROOT / "aws/manifests/latest.json").read_text())
    jsonschema.validate(latest, _schema("latest.schema.json"), format_checker=checker)
    LatestPointer.model_validate(latest)
    manifest = json.loads((PRICING_ROOT / latest["manifest_path"]).read_text())
    jsonschema.validate(manifest, _schema("manifest.schema.json"), format_checker=checker)
    assert Manifest.model_validate(manifest).status == "succeeded"


def test_minor_version_with_unknown_optional_fields_parses():
    document = json.loads((FIXTURES / "manifests" / "minor_bump_extra_field.json").read_text())
    assert "notes" in document  # an optional field the 1.0 models don't know
    manifest = Manifest.model_validate(document)
    assert manifest.manifest_version == "1.1"
