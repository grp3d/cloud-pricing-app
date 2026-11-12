"""Integration tests for the checked-in standard-architecture seed and migration `0005`
(014-architecture-templates-import-export, spec FR-001-FR-007, research.md §1-§2).

The seed file is validated with the same per-architecture validator the Admin import uses,
against whatever pricing dataset `PRICING_DATA_URI` points at (the real data locally, the
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
from src.pricing_data.active_snapshot import get_active_snapshot
from src.pricing_data.catalog import find_existing_skus
from src.pricing_data.providers.registry import get_provider
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


# --- 022: the GCP and Azure standard architectures -----------------------------------------

PROVIDER_REGIONS = {
    "gcp": {
        "Active-Standby Multi-Region Web Application": ["us-east1", "us-west1"],
        "Modern Data Lake & ETL Analytics Pipeline": ["us-east1"],
        "Serverless Microservices Back-End": ["europe-west1"],
        "Containerized Microservices Platform (EKS)": ["us-west1"],
    },
    "azure": {
        "Active-Standby Multi-Region Web Application": ["eastus", "westus2"],
        "Modern Data Lake & ETL Analytics Pipeline": ["eastus"],
        "Serverless Microservices Back-End": ["westeurope"],
        "Containerized Microservices Platform (EKS)": ["westus2"],
    },
}
NETWORK_TERM = {"gcp": "VPC", "azure": "VNet"}
# The GCP and Azure seeds' items are in their own fixture root (`build_provider_fixtures.py
# --standard-architectures`), so the small hand-picked fixture stays as other tests expect.
STANDARD_PRICING_ROOT = BACKEND / "tests" / "fixtures" / "pricing_parquet_standard"


def provider_seed(provider: str) -> ArchitectureExportFile:
    path = SEED_PATH.with_name(f"standard_architectures_{provider}.json")
    return ArchitectureExportFile.model_validate_json(path.read_text())


@pytest.mark.parametrize("provider", ["gcp", "azure"])
def test_provider_seed_has_the_four_designs_with_aws_names(provider):
    seed = provider_seed(provider)
    assert [a.name for a in seed.architectures] == list(EXPECTED)
    assert all(a.provider == provider for a in seed.architectures)


@pytest.mark.parametrize("provider", ["gcp", "azure"])
def test_provider_seed_has_one_collection_per_design_region(provider):
    """FR-002, FR-006: same collections in the same order, named in the provider's own term,
    and nothing else carried in the architectures' own fields."""
    for architecture in provider_seed(provider).architectures:
        actual = [(c.type.value, c.name, c.region, c.parent_ref) for c in architecture.collections]
        assert actual == [
            ("vpc", f"{NETWORK_TERM[provider]} ({region})", region, None)
            for region in PROVIDER_REGIONS[provider][architecture.name]
        ]
        assert architecture.connectors == []
        assert all(c.sku_selections for c in architecture.collections)


@pytest.mark.parametrize("provider", ["gcp", "azure"])
def test_provider_seed_selections_are_on_demand(provider):
    for architecture in provider_seed(provider).architectures:
        for collection in architecture.collections:
            for s in collection.sku_selections:
                assert (s.pricing_term.value, s.purchase_option.value) == (
                    "on_demand",
                    "not_applicable",
                )
                assert s.usage_quantity > 0


def test_gcp_machines_carry_vcpu_memory_and_ram_sku():
    """FR-004: the web app's and EKS nodes' Compute Engine machines are priced as cores + RAM."""
    options = [
        s.provider_options
        for a in provider_seed("gcp").architectures
        for c in a.collections
        for s in c.sku_selections
        if s.provider_options is not None
    ]
    machines = {(o.vcpus, o.memory_gib) for o in options}
    assert (4, 16) in machines  # e2-standard-4 for t4g.xlarge
    assert (2, 8) in machines  # e2-standard-2 for m6i.large
    assert all(o.kind == "gcp_machine" and o.ram_sku for o in options)


def test_azure_vms_carry_the_linux_os():
    options = [
        s.provider_options
        for a in provider_seed("azure").architectures
        for c in a.collections
        for s in c.sku_selections
        if s.provider_options is not None
    ]
    assert options, "the web app and EKS designs have VMs"
    assert all(o.kind == "azure_vm" and o.os == "linux" for o in options)


@pytest.mark.parametrize("provider", ["gcp", "azure"])
def test_provider_seed_passes_import_validation_against_pricing_data(provider, use_pricing_root):
    use_pricing_root(STANDARD_PRICING_ROOT)
    adapter = get_provider(provider)
    snapshot = get_active_snapshot(adapter.code)
    regions = set(list_available_regions(provider))
    for architecture in provider_seed(provider).architectures:
        definition, error = validate_definition(
            json.loads(architecture.model_dump_json()),
            taken_names=set(),
            available_regions=regions,
            existing_skus=lambda region, pairs: adapter.exists(snapshot, pairs, region=region),
        )
        assert error is None, f"{provider} {architecture.name}: {error}"


# --- 022 FR-009 / SC-006: the AWS seed and report are unchanged ----------------------------

AWS_SEED_SHA256 = {
    "standard_architectures.json": "2a2fd3f1292546e199271af065a89f908dbd2ea56abd85c6b1caff92693dd39b",
    "standard_architectures_report.md": (
        "2796f16c1c67ee804485887731f7a6939104a3e862c11e5bdda222382d91daca"
    ),
}


@pytest.mark.parametrize("name", sorted(AWS_SEED_SHA256))
def test_aws_seed_files_are_unchanged(name):
    import hashlib

    data = (SEED_PATH.parent / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == AWS_SEED_SHA256[name]


# --- 022 SC-005: generation is repeatable ----------------------------------------------------


@pytest.mark.parametrize("provider", ["gcp", "azure"])
def test_generation_reproduces_the_checked_in_seed_and_report(provider):
    """Resolving the rules against the standard-architecture fixture (which holds exactly the
    seeded items, copied verbatim from the snapshot they were generated from) gives byte-identical
    output to the checked-in files — and the same output every time."""
    import importlib

    from scripts.resolve_standard_architectures import (
        DEFAULT_SOURCE,
        RULE_MODULES,
        _outputs,
        _without_empty_options,
    )
    from scripts.standard_architectures.resolver import (
        render_report,
        resolve,
        to_export_file,
    )
    from src.pricing_data.active_snapshot import select_snapshot
    from src.pricing_data.snapshot import ActiveSnapshot
    from src.pricing_data.storage import LocalStore

    rules = importlib.import_module(RULE_MODULES[provider])
    source = json.loads(DEFAULT_SOURCE.read_text())
    store = LocalStore(STANDARD_PRICING_ROOT)
    selection = select_snapshot(store, provider, None, at_startup=True)
    snapshot = ActiveSnapshot.from_manifest(selection.manifest, base_dir=store.root, pinned=False)

    def generate() -> tuple[str, str]:
        resolution = resolve(
            rules.RULES, files=snapshot.files, snapshot_date=snapshot.snapshot_date,
            provider=provider,
        )
        export = to_export_file(resolution, source, provider=provider, regions=rules.REGIONS)
        seed = json.dumps(_without_empty_options(export.model_dump(mode="json")), indent=2) + "\n"
        return seed, render_report(resolution, source, provider=provider)

    first = generate()
    assert generate() == first
    seed_path, report_path = _outputs(provider)
    assert first == (seed_path.read_text(), report_path.read_text())


# --- 022 Story 4: the three versions of each design line up -------------------------------


def test_the_three_versions_of_each_design_share_name_and_shape(seed):
    gcp, azure = provider_seed("gcp"), provider_seed("azure")
    for aws_design, gcp_design, azure_design in zip(
        seed.architectures, gcp.architectures, azure.architectures, strict=True
    ):
        assert aws_design.name == gcp_design.name == azure_design.name
        assert (
            len(aws_design.collections)
            == len(gcp_design.collections)
            == len(azure_design.collections)
        )
