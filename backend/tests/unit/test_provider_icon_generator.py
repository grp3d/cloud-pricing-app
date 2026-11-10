"""Unit tests for the GCP / Azure service icon map generator (020, T015, research R5).

Hand-made icon folders under `tmp_path` and in-memory service lists: no real icon packages and
no Parquet.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "generate_provider_service_icon_map.py"


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location("generate_provider_service_icon_map", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _svg(path: Path, body: str = "<svg/>") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


@pytest.fixture
def gcp_icons(tmp_path):
    root = tmp_path / "gcp_architecture_icons"
    for stem in ("Compute-Engine", "Persistent-Disk", "Cloud-SQL", "Cloud-Storage",
                 "Cloud-Load-Balancing", "BigQuery"):
        _svg(root / "svg" / f"{stem}.svg", f"<svg id='{stem}'/>")
    return root


@pytest.fixture
def azure_icons(tmp_path):
    root = tmp_path / "azure_architecture_icons" / "Azure_Public_Service_Icons" / "Icons"
    _svg(root / "compute" / "10021-icon-service-Virtual-Machine.svg")
    _svg(root / "compute" / "10032-icon-service-Disks.svg")
    _svg(root / "networking" / "10062-icon-service-Load-Balancers.svg")
    # Duplicate names: the lowest-numbered file is the automatic choice.
    _svg(root / "other" / "02000-icon-service-Workspaces.svg", "<svg id='low'/>")
    _svg(root / "general" / "10500-icon-service-Workspaces.svg", "<svg id='high'/>")
    # The same file shipped in two category folders.
    _svg(root / "web" / "10035-icon-service-App-Services.svg")
    _svg(root / "compute" / "10035-icon-service-App-Services.svg")
    return tmp_path / "azure_architecture_icons"


def _service(gen, service_id, name, families=(), *, categorized=False, first_party=True):
    return gen.Service(service_id=service_id, name=name, families=tuple(families),
                       categorized=categorized, first_party=first_party)


# --- name normalization and icon indexing ------------------------------------------------------


def test_gcp_service_name_matches_its_icon_file(gen, gcp_icons):
    icons = gen.index_icons("gcp", gcp_icons)
    assert icons["Compute-Engine"].name == "Compute-Engine.svg"
    mapping = gen.build_mapping("gcp", [_service(gen, "CE", "Compute Engine")], icons, {}, {})
    assert mapping.by_id == {"CE": "Compute-Engine"}


def test_cloud_prefix_is_ignored_on_both_sides(gen, gcp_icons):
    icons = gen.index_icons("gcp", gcp_icons)
    services = [_service(gen, "SQL", "Cloud SQL"), _service(gen, "BQ", "BigQuery")]
    mapping = gen.build_mapping("gcp", services, icons, {}, {})
    assert mapping.by_id == {"SQL": "Cloud-SQL", "BQ": "BigQuery"}


def test_azure_plural_service_name_matches_singular_icon(gen, azure_icons):
    icons = gen.index_icons("azure", azure_icons)
    assert "Virtual-Machine" in icons
    mapping = gen.build_mapping("azure", [_service(gen, "VM", "Virtual Machines")], icons, {}, {})
    assert mapping.by_id == {"VM": "Virtual-Machine"}


def test_no_fuzzy_matches(gen, gcp_icons):
    icons = gen.index_icons("gcp", gcp_icons)
    services = [_service(gen, "M1", "MySQL by Bitnami"), _service(gen, "M2", "Compute Engines Pro")]
    mapping = gen.build_mapping("gcp", services, icons, {}, {})
    assert mapping.by_id == {}
    assert mapping.fallback == ["M1", "M2"]


def test_marketplace_services_never_match_automatically(gen, gcp_icons):
    icons = gen.index_icons("gcp", gcp_icons)
    services = [_service(gen, "MKT", "BigQuery", first_party=False)]
    mapping = gen.build_mapping("gcp", services, icons, {}, {})
    assert mapping.by_id == {}


def test_duplicate_azure_names_take_the_lowest_numbered_file(gen, azure_icons):
    icons = gen.index_icons("azure", azure_icons)
    assert icons["Workspaces"].name == "02000-icon-service-Workspaces.svg"
    assert icons["App-Services"].name == "10035-icon-service-App-Services.svg"


def test_an_override_can_name_another_duplicate_file(gen, azure_icons):
    icons = gen.index_icons("azure", azure_icons)
    assert "Workspaces@10500" in icons
    mapping = gen.build_mapping(
        "azure", [_service(gen, "W", "Workspaces")], icons, {"W": "Workspaces@10500"}, {})
    assert mapping.by_id == {"W": "Workspaces@10500"}
    assert mapping.used_stems == ["Workspaces@10500"]


# --- overrides ---------------------------------------------------------------------------------


def test_overrides_win_over_automatic_matches(gen, gcp_icons):
    icons = gen.index_icons("gcp", gcp_icons)
    mapping = gen.build_mapping(
        "gcp", [_service(gen, "CE", "Compute Engine")], icons, {"CE": "BigQuery"}, {})
    assert mapping.by_id == {"CE": "BigQuery"}
    assert mapping.overridden == ["CE"]


def test_an_override_of_none_forces_the_fallback(gen, gcp_icons):
    icons = gen.index_icons("gcp", gcp_icons)
    mapping = gen.build_mapping(
        "gcp", [_service(gen, "CE", "Compute Engine")], icons, {"CE": None}, {})
    assert mapping.by_id == {}
    assert mapping.fallback == ["CE"]


def test_an_override_naming_a_missing_icon_fails(gen, gcp_icons):
    icons = gen.index_icons("gcp", gcp_icons)
    with pytest.raises(SystemExit, match="Nope"):
        gen.build_mapping("gcp", [_service(gen, "CE", "Compute Engine")], icons, {"CE": "Nope"},
                          {})


def test_gcp_family_overrides_are_ordered_taxonomy_prefixes(gen, gcp_icons):
    icons = gen.index_icons("gcp", gcp_icons)
    families = ["Compute > Persistent Disk > SSD", "Network > Cloud LB > Proxy"]
    family_overrides = {"CE": [("Compute > Persistent Disk", "Persistent-Disk"),
                               ("Network > Cloud LB", "Cloud-Load-Balancing"),
                               ("Compute", "BigQuery")]}
    mapping = gen.build_mapping(
        "gcp", [_service(gen, "CE", "Compute Engine", families)], icons, {}, family_overrides)
    assert mapping.family_by_id == {"CE": [
        {"match": "Compute > Persistent Disk", "icon": "Persistent-Disk"},
        {"match": "Network > Cloud LB", "icon": "Cloud-Load-Balancing"},
        {"match": "Compute", "icon": "BigQuery"},
    ]}
    # First match wins: the disk family resolves to Persistent Disk, not the broader "Compute".
    assert gen.resolve("gcp", mapping, "CE", "Compute > Persistent Disk > SSD") == "Persistent-Disk"
    assert gen.resolve("gcp", mapping, "CE", "Compute > GCE > VMs On Demand") == "BigQuery"
    assert gen.resolve("gcp", mapping, "CE", "Analytics > Licenses") == "Compute-Engine"


def test_azure_family_overrides_are_case_insensitive_patterns(gen, azure_icons):
    icons = gen.index_icons("azure", azure_icons)
    family_overrides = {"ST": [("managed disks", "Disks")]}
    services = [_service(gen, "ST", "Virtual Machines", ["Premium SSD Managed Disks", "Blob"])]
    mapping = gen.build_mapping("azure", services, icons, {}, family_overrides)
    assert gen.resolve("azure", mapping, "ST", "Premium SSD Managed Disks") == "Disks"
    assert gen.resolve("azure", mapping, "ST", "Blob") == "Virtual-Machine"


def test_a_family_override_that_matches_nothing_is_reported(gen, gcp_icons):
    icons = gen.index_icons("gcp", gcp_icons)
    mapping = gen.build_mapping(
        "gcp", [_service(gen, "CE", "Compute Engine", ["Compute > GCE"])], icons, {},
        {"CE": [("Storage > Nothing", "Cloud-Storage")]})
    assert any("Storage > Nothing" in line and "matches no product" in line
               for line in mapping.report)


# --- outputs -----------------------------------------------------------------------------------


def test_output_is_deterministic(gen, gcp_icons):
    icons = gen.index_icons("gcp", gcp_icons)
    services = [_service(gen, "SQL", "Cloud SQL"), _service(gen, "CE", "Compute Engine",
                                                            ["Compute > Persistent Disk"])]
    family = {"CE": [("Compute > Persistent Disk", "Persistent-Disk")]}
    first = gen.render_ts("gcp", gen.build_mapping("gcp", services, icons, {}, family))
    second = gen.render_ts("gcp", gen.build_mapping("gcp", list(reversed(services)), icons, {},
                                                    family))
    assert first == second
    assert "export const GCP_SERVICE_ICON_BY_ID" in first
    assert "export const GCP_SERVICE_ICON_OVERRIDES" in first
    assert first.index("  CE:") < first.index("  SQL:")


def test_keys_are_quoted_only_when_needed(gen, gcp_icons):
    """The output is prettier-clean as written (quoteProps "as-needed")."""
    icons = gen.index_icons("gcp", gcp_icons)
    ts = gen.render_ts("gcp", gen.build_mapping(
        "gcp", [_service(gen, "6F81-5844-456A", "Compute Engine"),
                _service(gen, "DZH313", "Cloud SQL")], icons, {}, {}))
    assert '  "6F81-5844-456A": "Compute-Engine",' in ts
    assert '  DZH313: "Cloud-SQL",' in ts


def test_azure_exports_are_named_for_azure(gen, azure_icons):
    icons = gen.index_icons("azure", azure_icons)
    ts = gen.render_ts("azure", gen.build_mapping("azure", [], icons, {}, {}))
    assert "export const AZURE_SERVICE_ICON_BY_ID" in ts
    assert "export const AZURE_SERVICE_ICON_OVERRIDES" in ts


def test_only_referenced_svgs_are_copied(gen, gcp_icons, tmp_path):
    icons = gen.index_icons("gcp", gcp_icons)
    services = [_service(gen, "CE", "Compute Engine", ["Compute > Persistent Disk"])]
    mapping = gen.build_mapping("gcp", services, icons, {},
                                {"CE": [("Compute > Persistent Disk", "Persistent-Disk")]})
    assert mapping.used_stems == ["Compute-Engine", "Persistent-Disk"]
    out = tmp_path / "out"
    out.mkdir()
    (out / "README.md").write_text("keep me")
    (out / "Stale.svg").write_text("<svg/>")
    gen.copy_icons(icons, mapping.used_stems, out)
    assert sorted(p.name for p in out.iterdir()) == [
        "Compute-Engine.svg", "Persistent-Disk.svg", "README.md"]
    # Copied unmodified.
    assert (out / "Compute-Engine.svg").read_text() == "<svg id='Compute-Engine'/>"


def test_report_lists_categorized_services_without_an_icon(gen, gcp_icons):
    icons = gen.index_icons("gcp", gcp_icons)
    services = [
        _service(gen, "CE", "Compute Engine", categorized=True),
        _service(gen, "XX", "Some Database Thing", categorized=True),
        _service(gen, "MK", "Marketplace App", categorized=False, first_party=False),
    ]
    mapping = gen.build_mapping("gcp", services, icons, {}, {})
    assert mapping.uncovered == ["XX"]
    text = "\n".join(mapping.report)
    assert "categorized services without an icon (1)" in text
    assert "Some Database Thing" in text


def test_categorization_follows_the_seed_rules(gen):
    rules = gen.load_category_rules()
    assert gen.gcp_categorized(["Compute", "GCE", "VMs On Demand"], rules)
    assert gen.gcp_categorized(["Analytics", "Egress"], rules)  # level 2 rule
    assert not gen.gcp_categorized(["Marketplace Services", "Ubuntu"], rules)
    assert gen.azure_categorized("Networking", "Anything", rules)
    assert gen.azure_categorized("Containers", "Container Instances", rules)
    assert not gen.azure_categorized("AI + Machine Learning", "Cognitive Services", rules)
