"""Resolve standard-architecture match rules to concrete pricing-data SKUs
(014-architecture-templates-import-export, research.md §1-§5).

Deterministic by construction: each rule's candidates are tried in order, and among the SKUs
matching every filter the lowest `sku` wins — "the first available match" of spec FR-008, made
reproducible. A chosen SKU billed in a unit the pricing engine can't classify fails the whole
run (research.md §6) rather than seeding an entry that would silently show as unpriceable.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import duckdb

from scripts.standard_architectures.match_rules import MatchRule
from src.models.schemas import (
    EXPORT_FORMAT,
    ArchitectureDefinition,
    ArchitectureExportFile,
    CollectionDefinition,
    SKUSelectionDefinition,
)
from src.pricing_data.duration import classify_unit
from src.pricing_data.providers.units import parse_azure_unit, parse_gcp_unit


class UnrecognizedUnitError(RuntimeError):
    """A chosen SKU's On-Demand unit isn't in `pricing_data/duration.py`'s tables."""


@dataclass(frozen=True)
class GcpMachine:
    """022 research R6: a GCP machine (or Cloud SQL instance) priced as vCPUs x the core SKU's
    rate plus GiB x the RAM SKU's rate. The rule's own filters find the core SKU; these find
    the matching RAM SKU (billed per `GiBy.h`)."""

    vcpus: int
    memory_gib: Decimal
    ram_filters: dict[str, str] = field(default_factory=dict)
    ram_patterns: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderRule:
    """022 research R4: one usage figure of one AWS reference component, matched on GCP or
    Azure. `component_id` is the AWS reference component this stands in for (FR-011).

    `filters` are exact column equalities and `patterns` full-string regular expressions, on the
    provider's own columns (`_GCP_COLUMNS`, `_AZURE_COLUMNS`). `expected_unit` is the source
    unit as published (GCP `unit`, Azure `unit_of_measure`)."""

    architecture_id: str
    component_id: str
    figure: str
    region: str
    filters: dict[str, str] = field(default_factory=dict)
    patterns: dict[str, str] = field(default_factory=dict)
    expected_unit: str | None = None
    quantity: Decimal = Decimal(0)
    machine: GcpMachine | None = None
    azure_os: str | None = None
    size_note: str | None = None
    omit_reason: str | None = None
    note: str | None = None


AnyRule = MatchRule | ProviderRule


@dataclass(frozen=True)
class Match:
    rule: AnyRule
    service_code: str
    sku: str
    unit: str
    # More than one On-Demand price row (usage tiers) — the existing price lookup takes the
    # first row read, so the report flags these (research.md §7.3).
    tiered: bool
    # 022: `gcp_machine` / `azure_vm` options for the selection; None otherwise.
    provider_options: dict[str, Any] | None = None


@dataclass(frozen=True)
class Omission:
    rule: AnyRule
    reason: str


@dataclass(frozen=True)
class Resolution:
    snapshot_date: str
    matches: list[Match]
    omissions: list[Omission]


# 018-app-cloud-deployment: (table, region) -> the data files to read, from a snapshot's
# manifest (`ActiveSnapshot.files`), never a folder layout.
FilesFor = Callable[[str, str], list[str]]


def _find(
    con: duckdb.DuckDBPyConnection,
    rule: MatchRule,
    service_code: str,
    *,
    files: FilesFor,
) -> Match | None:
    product_dim = files("product_dim", rule.region)
    price_fact = files("price_fact", rule.region)

    # Region-scoped the same way as `pricing_data/catalog.py`: a partition also holds rows for
    # other regions, and AWSDataTransfer's own region_code is unreliable.
    conditions = [
        "pd.service_code = ?",
        "CASE WHEN regexp_matches(pd.service_code, 'AWSDataTransfer', 'i') "
        "THEN json_extract_string(pd.attributes_json, '$.fromRegionCode') = ? "
        "ELSE pd.region_code = ? END",
    ]
    params: list[Any] = [service_code, rule.region, rule.region]
    if rule.product_family is not None:
        conditions.append("pd.product_family = ?")
        params.append(rule.product_family)
    for key, value in sorted(rule.attribute_filters.items()):
        conditions.append("json_extract_string(pd.attributes_json, ?) = ?")
        params.extend([f"$.{key}", value])
    unit_condition = ""
    unit_params: list[Any] = []
    if rule.expected_unit is not None:
        unit_condition = " AND pf.unit = ?"
        unit_params.append(rule.expected_unit)

    row = con.execute(
        f"""
        SELECT pd.sku FROM read_parquet(?) pd
        WHERE {" AND ".join(conditions)}
          AND EXISTS (
            SELECT 1 FROM read_parquet(?) pf
            WHERE pf.sku = pd.sku AND pf.term = 'OnDemand'{unit_condition}
          )
        ORDER BY pd.sku
        LIMIT 1
        """,
        [product_dim, *params, price_fact, *unit_params],
    ).fetchone()
    if row is None:
        return None
    sku = row[0]

    units = con.execute(
        "SELECT unit, count(*) FROM read_parquet(?) WHERE sku = ? AND term = 'OnDemand' "
        "GROUP BY unit ORDER BY unit",
        [price_fact, sku],
    ).fetchall()
    if rule.expected_unit is not None:
        unit = rule.expected_unit
        rows_for_unit = dict(units)[unit]
    else:
        unit, rows_for_unit = units[0]
    if classify_unit(unit).category == "unrecognized":
        raise UnrecognizedUnitError(
            f"{rule.architecture_id}/{rule.component_id}/{rule.figure}: {service_code} {sku} "
            f"bills in unit {unit!r}, which pricing_data/duration.py doesn't recognize"
        )
    return Match(rule=rule, service_code=service_code, sku=sku, unit=unit, tiered=rows_for_unit > 1)


GLOBAL = "global"

# 022: the columns a GCP or Azure rule may filter on (never interpolated from anywhere else).
_GCP_COLUMNS = frozenset(
    {"service_name", "service_id", "sku_id", "display_name", "geo_taxonomy_type", "taxonomy"}
)
_AZURE_COLUMNS = frozenset(
    {
        "service_family", "service_name", "service_id", "product_name", "sku_id", "sku_name",
        "arm_sku_name", "meter_id", "meter_name",
    }
)


def _conditions(
    filters: dict[str, str], patterns: dict[str, str], allowed: frozenset[str], alias: str
) -> tuple[list[str], list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    for kind, mapping in (("=", filters), ("~", patterns)):
        for column, value in sorted(mapping.items()):
            if column not in allowed:
                raise ValueError(f"unknown filter column {column!r}")
            ref = f"{alias}.{column}"
            if kind == "=":
                conditions.append(f"{ref} = ?")
            else:
                conditions.append(f"regexp_full_match({ref}, ?)")
            params.append(value)
    return conditions, params


def _gcp_lookup(
    con: duckdb.DuckDBPyConnection,
    region: str,
    filters: dict[str, str],
    patterns: dict[str, str],
    expected_unit: str | None,
    *,
    files: FilesFor,
) -> tuple[str, str, str, str] | None:
    """(service_id, sku_id, location, consumption_model) of the lowest matching `Default`-priced
    SKU in the region or `global`, as `providers/gcp.py` prices it (region first)."""
    locations = [region] if region == GLOBAL else [region, GLOBAL]
    sku_files = [f for loc in locations for f in files("sku", loc)]
    price_files = [f for loc in locations for f in files("sku_price", loc)]
    service_files = files("service", GLOBAL)
    if not sku_files or not price_files:
        return None
    conditions, params = _conditions(filters, patterns, _GCP_COLUMNS, "k")
    unit_condition = " AND p.unit = ?" if expected_unit is not None else ""
    service_cte = (
        "SELECT service_id, any_value(display_name) AS service_name FROM read_parquet(?) "
        "GROUP BY service_id"
        if service_files
        else "SELECT NULL::VARCHAR AS service_id, NULL::VARCHAR AS service_name WHERE false"
    )
    row = con.execute(
        f"""
        WITH svc AS ({service_cte}),
        k AS (
            SELECT s.location, s.sku_id, s.service_id, s.display_name, s.geo_taxonomy_type,
                array_to_string(s.product_taxonomy, ' > ') AS taxonomy, svc.service_name
            FROM read_parquet(?) s LEFT JOIN svc USING (service_id)
        )
        SELECT k.service_id, k.sku_id, k.location, p.consumption_model FROM k
        JOIN read_parquet(?) p ON p.sku_id = k.sku_id AND p.location = k.location
        WHERE k.location IN ({",".join("?" for _ in locations)})
          AND p.consumption_model_description = 'Default'{unit_condition}
          {"".join(f" AND {c}" for c in conditions)}
        ORDER BY k.location = 'global', k.sku_id
        LIMIT 1
        """,
        [
            *([service_files] if service_files else []),
            sku_files,
            price_files,
            *locations,
            *([expected_unit] if expected_unit is not None else []),
            *params,
        ],
    ).fetchone()
    return None if row is None else (row[0], row[1], row[2], row[3])


def _find_gcp(
    con: duckdb.DuckDBPyConnection, rule: ProviderRule, *, files: FilesFor
) -> Match | Omission:
    found = _gcp_lookup(
        con, rule.region, rule.filters, rule.patterns, rule.expected_unit, files=files
    )
    if found is None:
        return Omission(rule=rule, reason=f"no matching SKU in {rule.region} with the rule's filters")
    service_id, sku, location, model = found
    locations = [location]
    unit, unit_quantity = con.execute(
        "SELECT unit, unit_quantity FROM read_parquet(?) WHERE sku_id = ? AND location = ? "
        "AND consumption_model = ? LIMIT 1",
        [list(files("sku_price", location)), sku, location, model],
    ).fetchone()
    if parse_gcp_unit(unit, unit_quantity).classification.category == "unrecognized":
        raise UnrecognizedUnitError(
            f"{rule.architecture_id}/{rule.component_id}/{rule.figure}: GCP {sku} bills in unit "
            f"{unit!r}, which providers/units.py doesn't recognize"
        )
    tier_files = [f for loc in locations for f in files("sku_price_tier", loc)]
    tiers = (
        con.execute(
            "SELECT count(*) FROM read_parquet(?) WHERE sku_id = ? AND location = ? "
            "AND consumption_model = ?",
            [tier_files, sku, location, model],
        ).fetchone()[0]
        if tier_files
        else 0
    )
    options = None
    if rule.machine is not None:
        ram = _gcp_lookup(
            con, rule.region, {**rule.filters, **rule.machine.ram_filters},
            {k: v for k, v in rule.patterns.items() if k not in rule.machine.ram_patterns}
            | rule.machine.ram_patterns,
            "GiBy.h", files=files,
        )
        if ram is None:
            return Omission(rule=rule, reason=f"no matching RAM SKU in {rule.region} for the machine")
        options = {
            "kind": "gcp_machine",
            "version": 1,
            "vcpus": rule.machine.vcpus,
            "memory_gib": str(rule.machine.memory_gib),
            "ram_sku": ram[1],
        }
    return Match(
        rule=rule, service_code=service_id, sku=sku, unit=unit, tiered=tiers > 1,
        provider_options=options,
    )


def _find_azure(
    con: duckdb.DuckDBPyConnection, rule: ProviderRule, *, files: FilesFor
) -> Match | Omission:
    """The lowest matching `Consumption` meter (`<sku_id>/<meter_id>`, `providers/azure.py`)
    in the region or `global`."""
    locations = [rule.region] if rule.region == GLOBAL else [rule.region, GLOBAL]
    item_files = [f for loc in locations for f in files("price_item", loc)]
    reason = f"no matching meter in {rule.region} with the rule's filters"
    if not item_files:
        return Omission(rule=rule, reason=reason)
    conditions, params = _conditions(rule.filters, rule.patterns, _AZURE_COLUMNS, "i")
    unit_condition = " AND i.unit_of_measure = ?" if rule.expected_unit is not None else ""
    row = con.execute(
        f"""
        SELECT i.service_id, i.sku_id, i.meter_id, i.location, i.unit_of_measure
        FROM read_parquet(?) i
        WHERE i.location IN ({",".join("?" for _ in locations)})
          AND i.price_type = 'Consumption'{unit_condition}
          {"".join(f" AND {c}" for c in conditions)}
        ORDER BY i.location = 'global', i.sku_id, i.meter_id
        LIMIT 1
        """,
        [
            item_files,
            *locations,
            *([rule.expected_unit] if rule.expected_unit is not None else []),
            *params,
        ],
    ).fetchone()
    if row is None:
        return Omission(rule=rule, reason=reason)
    service_id, sku_id, meter_id, location, unit = row
    if parse_azure_unit(unit).classification.category == "unrecognized":
        raise UnrecognizedUnitError(
            f"{rule.architecture_id}/{rule.component_id}/{rule.figure}: Azure {sku_id}/{meter_id} "
            f"bills in unit {unit!r}, which providers/units.py doesn't recognize"
        )
    tiers = con.execute(
        "SELECT count(*) FROM read_parquet(?) WHERE location = ? AND sku_id = ? AND meter_id = ? "
        "AND price_type = 'Consumption'",
        [item_files, location, sku_id, meter_id],
    ).fetchone()[0]
    options = (
        {"kind": "azure_vm", "version": 1, "os": rule.azure_os} if rule.azure_os is not None else None
    )
    return Match(
        rule=rule, service_code=service_id, sku=f"{sku_id}/{meter_id}", unit=unit,
        tiered=tiers > 1, provider_options=options,
    )


def resolve(
    rules: Sequence[AnyRule], *, files: FilesFor, snapshot_date: str, provider: str = "aws"
) -> Resolution:
    matches: list[Match] = []
    omissions: list[Omission] = []
    con: duckdb.DuckDBPyConnection | None = None
    for rule in rules:
        if rule.omit_reason is not None:
            omissions.append(Omission(rule=rule, reason=rule.omit_reason))
            continue
        if con is None:
            con = duckdb.connect(":memory:")
        if provider != "aws":
            assert isinstance(rule, ProviderRule)
            finder = _find_gcp if provider == "gcp" else _find_azure
            outcome = finder(con, rule, files=files)
            (matches if isinstance(outcome, Match) else omissions).append(outcome)
            continue
        match = None
        for service_code in rule.service_codes:
            match = _find(con, rule, service_code, files=files)
            if match is not None:
                break
        if match is None:
            omissions.append(
                Omission(
                    rule=rule,
                    reason=(
                        f"no matching SKU in {rule.region} for "
                        f"{' / '.join(rule.service_codes)} with the rule's filters"
                    ),
                )
            )
        else:
            matches.append(match)
    return Resolution(
        snapshot_date=snapshot_date, matches=matches, omissions=omissions
    )


# 022 research R8: each provider's own term for the network a collection stands for.
_NETWORK_TERM = {"aws": "VPC", "gcp": "VPC", "azure": "VNet"}


def to_export_file(
    resolution: Resolution,
    source: dict[str, Any],
    *,
    provider: str = "aws",
    regions: dict[str, str] | None = None,
) -> ArchitectureExportFile:
    """Build the seed in the export format: one VPC per listed region (source order), each
    holding its region's matched entries in rule order. No connectors or application
    components (spec FR-005, FR-007).

    022: for GCP and Azure, `regions` maps each AWS reference region to the provider's region
    (research R1); collections are named in the provider's own term (research R8)."""
    regions = regions or {}
    architectures = []
    for arch in source["architectures"]:
        collections = []
        for index, aws_region in enumerate(arch["regions"], start=1):
            region = regions.get(aws_region, aws_region)
            selections = [
                SKUSelectionDefinition(
                    service_code=m.service_code,
                    sku=m.sku,
                    pricing_term="on_demand",
                    purchase_option="not_applicable",
                    usage_quantity=m.rule.quantity,
                    provider_options=m.provider_options,
                )
                for m in resolution.matches
                if m.rule.architecture_id == arch["id"] and m.rule.region == region
            ]
            collections.append(
                CollectionDefinition(
                    ref=f"c{index}",
                    type="vpc",
                    name=f"{_NETWORK_TERM[provider]} ({region})",
                    region=region,
                    parent_ref=None,
                    sku_selections=selections,
                )
            )
        architectures.append(
            ArchitectureDefinition(
                name=arch["name"], provider=provider, collections=collections, connectors=[]
            )
        )
    return ArchitectureExportFile(
        format=EXPORT_FORMAT,
        format_version=1,
        # Deterministic (not "now") so re-running against the same snapshot is byte-identical.
        exported_at=datetime.fromisoformat(f"{resolution.snapshot_date}T00:00:00+00:00"),
        source_username="Admin",
        architectures=architectures,
    )


def render_report(
    resolution: Resolution, source: dict[str, Any] | None = None, *, provider: str = "aws"
) -> str:
    """The resolution report. AWS keeps its 014 layout; GCP and Azure (022, contracts/
    generator.md) name the provider, the AWS component each row stands in for, and the original
    and chosen sizes."""
    names = {a["id"]: a["name"] for a in (source or {}).get("architectures", [])}
    architecture_ids = list(
        dict.fromkeys(
            [m.rule.architecture_id for m in resolution.matches]
            + [o.rule.architecture_id for o in resolution.omissions]
        )
    )
    aws = provider == "aws"
    lines = [
        "# Standard architectures — resolution report",
        "",
        "Generated by `scripts/resolve_standard_architectures.py` — do not edit by hand.",
        "",
    ]
    if not aws:
        lines += [f"Provider: `{provider}`", ""]
    lines += [
        f"Pricing snapshot: `{resolution.snapshot_date}`",
        "",
        "`tiered` marks SKUs with more than one On-Demand price row (usage tiers); the price "
        "lookup uses the first row read (research.md §7.3).",
    ]
    if not aws:
        lines += [
            "",
            "Each row names the AWS reference component it stands in for. `Size` gives the AWS "
            "original and the chosen size: the smallest with at least the same vCPU and memory "
            "(022 clarification).",
        ]
    component = "Component" if aws else "AWS component"
    for arch_id in architecture_ids:
        lines += ["", f"## {names.get(arch_id, arch_id)}", ""]
        if aws:
            lines += [
                "| Component | Figure | Region | Service | SKU | Unit | Quantity | Tiered | Note |",
                "|---|---|---|---|---|---|---|---|---|",
            ]
        else:
            lines += [
                "| AWS component | Figure | Region | Service | SKU | Unit | Quantity | Tiered | "
                "Size | Note |",
                "|---|---|---|---|---|---|---|---|---|---|",
            ]
        for m in resolution.matches:
            if m.rule.architecture_id != arch_id:
                continue
            r = m.rule
            size = "" if aws else f" {getattr(r, 'size_note', None) or ''} |"
            lines.append(
                f"| {r.component_id} | {r.figure} | {r.region} | {m.service_code} | {m.sku} | "
                f"{m.unit} | {r.quantity} | {'yes' if m.tiered else ''} |{size} {r.note or ''} |"
            )
        omitted = [o for o in resolution.omissions if o.rule.architecture_id == arch_id]
        if omitted:
            lines += [
                "", "**Left out**", "", f"| {component} | Figure | Reason |", "|---|---|---|",
            ]
            for o in omitted:
                lines.append(f"| {o.rule.component_id} | {o.rule.figure} | {o.reason} |")
    return "\n".join(lines) + "\n"


# --- 026: seed mappings ---------------------------------------------------------------------------
# 026-agent-cross-cloud-translation, research R4: the AWS rules and one provider's rules, paired by
# (architecture, component, figure), become mappings from the AWS product's key to the provider
# product's key. `key_of(provider, service_code, sku, region)` gives a product key (research R2).

SERVICE_MAPPINGS_FORMAT = "cloud-pricing-service-mappings"
SERVICE_MAPPINGS_VERSION = 1

KeyOf = Callable[[str, str, str, str], str]


def _figure(rule: AnyRule) -> tuple[str, str, str]:
    return (rule.architecture_id, rule.component_id, rule.figure)


def _factor(target: Decimal, source: Decimal) -> str | None:
    """Target ÷ source at full precision: the source's 4-decimal quantity × factor, rounded to 4
    decimals, gives back the seed's quantity."""
    if not source:
        return None
    return f"{(target / source).normalize():f}"


def _target_options(match: Match, key_of: KeyOf) -> dict[str, Any] | None:
    """The match's options without region-bound SKUs: a GCP machine's RAM SKU becomes its key."""
    options = dict(match.provider_options or {})
    if not options:
        return None
    ram_sku = options.pop("ram_sku", None)
    if ram_sku:
        options["ram_key"] = key_of("gcp", match.service_code, ram_sku, match.rule.region)
    return options


def to_service_mappings(aws: Resolution, target: Resolution, *, target_provider: str,
                        key_of: KeyOf, version: int = SERVICE_MAPPINGS_VERSION) -> dict[str, Any]:
    """The seed mapping file for one target provider (data-model.md §1). Sorted and stable."""
    sources = {_figure(m.rule): m for m in aws.matches}
    parts: dict[tuple[str, str, str], list[Match]] = {}
    for m in target.matches:
        parts.setdefault(_figure(m.rule), []).append(m)
    omitted = {_figure(o.rule): o.reason for o in target.omissions}
    # An alternative is told apart by its target keys, factors and options; the region-bound SKU
    # and the note of its first occurrence go with it.
    alternatives: dict[str, list[tuple]] = {}
    extras: dict[tuple[str, tuple], list[tuple[str, str | None]]] = {}
    for figure, source in sources.items():
        source_key = key_of("aws", source.service_code, source.sku, source.rule.region)
        if figure in parts:
            lines = tuple(
                (key_of(target_provider, m.service_code, m.sku, m.rule.region), m.service_code,
                 json.dumps(_target_options(m, key_of), sort_keys=True),
                 _factor(m.rule.quantity, source.rule.quantity))
                for m in parts[figure])
            alternative: tuple = ("match", lines)
            extra = [(m.sku, getattr(m.rule, "note", None) or getattr(m.rule, "size_note", None))
                     for m in parts[figure]]
        elif figure in omitted:
            alternative, extra = ("omit", omitted[figure]), []
        else:
            continue
        seen = alternatives.setdefault(source_key, [])
        if alternative not in seen:
            seen.append(alternative)
            extras[(source_key, alternative)] = extra
    rows: list[dict[str, Any]] = []
    for source_key in sorted(alternatives):
        for number, (kind, value) in enumerate(alternatives[source_key], start=1):
            if kind == "omit":
                rows.append({"source_key": source_key, "alternative": number, "part": 1,
                             "target_key": None, "target_service_code": None,
                             "target_sku": None, "target_options": None,
                             "quantity_factor": None, "note": None, "omit_reason": value})
                continue
            extra = extras[(source_key, (kind, value))]
            for part, ((key, service_code, options, factor), (sku, note)) in enumerate(
                    zip(value, extra, strict=True), 1):
                rows.append({"source_key": source_key, "alternative": number, "part": part,
                             "target_key": key, "target_service_code": service_code,
                             "target_sku": sku, "target_options": json.loads(options),
                             "quantity_factor": factor, "note": note, "omit_reason": None})
    return {"format": SERVICE_MAPPINGS_FORMAT, "version": version, "source_provider": "aws",
            "target_provider": target_provider,
            "snapshots": {"aws": aws.snapshot_date, target_provider: target.snapshot_date},
            "mappings": rows}
