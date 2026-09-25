"""Integration tests for the checked-in standard-architecture seed and migration `0005`
(014-architecture-templates-import-export, spec FR-001-FR-007, research.md §1-§2).

The seed file is validated with the same per-architecture validator the Admin import uses,
against whatever pricing dataset `AWS_PRICING_PARQUET_DIR` points at (the real data locally, the
Parquet fixture in CI) — proving every seeded SKU exists in the region it will be priced in.
The migration's insert function runs inside a transaction that is rolled back, since
`conftest.py` truncates architectures between tests anyway.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from src.models.schemas import ArchitectureExportFile
from src.pricing_data.catalog import find_existing_skus
from src.pricing_data.regions import list_available_regions
from src.services.architecture_transfer import validate_definition

BACKEND = Path(__file__).resolve().parents[2]
SEED_PATH = BACKEND / "src" / "db" / "seed" / "standard_architectures.json"
MIGRATION_PATH = (
    BACKEND / "src" / "db" / "migrations" / "versions" / "0005_standard_architectures.py"
)
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://localhost/cloud_pricing_test"
)

EXPECTED = {
    "Active-Standby Multi-Region Web Application": ["us-east-1", "us-west-2"],
    "Modern Data Lake & ETL Analytics Pipeline": ["us-east-1"],
    "Serverless Microservices Back-End": ["eu-west-1"],
    "Containerized Microservices Platform (EKS)": ["us-west-2"],
}


@pytest.fixture(scope="module")
def seed() -> ArchitectureExportFile:
    return ArchitectureExportFile.model_validate_json(SEED_PATH.read_text())


def test_seed_has_exactly_the_four_standard_architectures(seed):
    assert [a.name for a in seed.architectures] == list(EXPECTED)
    assert all(a.provider == "aws" for a in seed.architectures)


def test_one_vpc_per_listed_region_and_nothing_else(seed):
    for architecture in seed.architectures:
        actual = [(c.type.value, c.name, c.region, c.parent_ref) for c in architecture.collections]
        assert actual == [
            ("vpc", f"VPC ({region})", region, None) for region in EXPECTED[architecture.name]
        ]
        assert architecture.connectors == []
        assert all(c.sku_selections for c in architecture.collections)


def test_global_components_sit_in_the_first_regions_vpc(seed):
    """Route 53 (the only global component with pricing records) goes in us-east-1's VPC."""
    web = seed.architectures[0]
    first_vpc_services = {s.service_code for s in web.collections[0].sku_selections}
    second_vpc_services = {s.service_code for s in web.collections[1].sku_selections}
    assert "AmazonRoute53" in first_vpc_services
    assert "AmazonRoute53" not in second_vpc_services


def test_every_selection_is_on_demand(seed):
    for architecture in seed.architectures:
        for collection in architecture.collections:
            for s in collection.sku_selections:
                assert (s.pricing_term.value, s.purchase_option.value) == (
                    "on_demand",
                    "not_applicable",
                )
                assert s.usage_quantity > 0


def test_seed_passes_import_validation_against_pricing_data(seed):
    regions = set(list_available_regions())
    for architecture in seed.architectures:
        definition, error = validate_definition(
            json.loads(architecture.model_dump_json()),
            taken_names=set(),
            available_regions=regions,
            existing_skus=lambda region, pairs: find_existing_skus(pairs, region=region),
        )
        assert error is None, f"{architecture.name}: {error}"


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_0005", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_inserts_public_admin_architectures_once(seed):
    migration = _load_migration()
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                migration.insert_standard_architectures(conn)
                rows = conn.execute(
                    text(
                        "SELECT a.name, a.is_public, a.provider, "
                        "  (SELECT count(*) FROM collections c WHERE c.architecture_id = a.id), "
                        "  (SELECT count(*) FROM sku_selections s "
                        "     JOIN collections c ON c.id = s.collection_id "
                        "     WHERE c.architecture_id = a.id) "
                        "FROM architectures a JOIN users u ON u.id = a.user_id "
                        "WHERE u.is_default_admin ORDER BY a.name"
                    )
                ).fetchall()
                expected = sorted(
                    (
                        a.name,
                        True,
                        "aws",
                        len(a.collections),
                        sum(len(c.sku_selections) for c in a.collections),
                    )
                    for a in seed.architectures
                )
                assert [tuple(r) for r in rows] == expected

                # A second run (e.g. a re-applied migration) adds nothing — name guard.
                migration.insert_standard_architectures(conn)
                count = conn.execute(
                    text(
                        "SELECT count(*) FROM architectures a JOIN users u ON u.id = a.user_id "
                        "WHERE u.is_default_admin"
                    )
                ).scalar_one()
                assert count == 4
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
