"""Resolve standard-architecture match rules to concrete pricing-data SKUs
(014-architecture-templates-import-export, research.md §1-§5).

Deterministic by construction: each rule's candidates are tried in order, and among the SKUs
matching every filter the lowest `sku` wins — "the first available match" of spec FR-008, made
reproducible. A chosen SKU billed in a unit the pricing engine can't classify fails the whole
run (research.md §6) rather than seeding an entry that would silently show as unpriceable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
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


class UnrecognizedUnitError(RuntimeError):
    """A chosen SKU's On-Demand unit isn't in `pricing_data/duration.py`'s tables."""


@dataclass(frozen=True)
class Match:
    rule: MatchRule
    service_code: str
    sku: str
    unit: str
    # More than one On-Demand price row (usage tiers) — the existing price lookup takes the
    # first row read, so the report flags these (research.md §7.3).
    tiered: bool


@dataclass(frozen=True)
class Omission:
    rule: MatchRule
    reason: str


@dataclass(frozen=True)
class Resolution:
    snapshot_date: str
    matches: list[Match]
    omissions: list[Omission]


def _partition(parquet_dir: Path, table: str, snapshot_date: str, region: str) -> str:
    return str(
        Path(parquet_dir) / table / f"snapshot_date={snapshot_date}" / f"region={region}"
        / "part-0.parquet"
    )


def _find(
    con: duckdb.DuckDBPyConnection,
    rule: MatchRule,
    service_code: str,
    *,
    parquet_dir: Path,
    snapshot_date: str,
) -> Match | None:
    product_dim = _partition(parquet_dir, "product_dim", snapshot_date, rule.region)
    price_fact = _partition(parquet_dir, "price_fact", snapshot_date, rule.region)

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


def resolve(
    rules: Sequence[MatchRule], *, parquet_dir: Path | str, snapshot_date: str
) -> Resolution:
    parquet_dir = Path(parquet_dir)
    matches: list[Match] = []
    omissions: list[Omission] = []
    con: duckdb.DuckDBPyConnection | None = None
    for rule in rules:
        if rule.omit_reason is not None:
            omissions.append(Omission(rule=rule, reason=rule.omit_reason))
            continue
        if con is None:
            con = duckdb.connect(":memory:")
        match = None
        for service_code in rule.service_codes:
            match = _find(
                con, rule, service_code, parquet_dir=parquet_dir, snapshot_date=snapshot_date
            )
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


def to_export_file(resolution: Resolution, source: dict[str, Any]) -> ArchitectureExportFile:
    """Build the seed in the export format: one VPC per listed region (source order), each
    holding its region's matched entries in rule order. No connectors or application
    components (spec FR-005, FR-007)."""
    architectures = []
    for arch in source["architectures"]:
        collections = []
        for index, region in enumerate(arch["regions"], start=1):
            selections = [
                SKUSelectionDefinition(
                    service_code=m.service_code,
                    sku=m.sku,
                    pricing_term="on_demand",
                    purchase_option="not_applicable",
                    usage_quantity=m.rule.quantity,
                )
                for m in resolution.matches
                if m.rule.architecture_id == arch["id"] and m.rule.region == region
            ]
            collections.append(
                CollectionDefinition(
                    ref=f"c{index}",
                    type="vpc",
                    name=f"VPC ({region})",
                    region=region,
                    parent_ref=None,
                    sku_selections=selections,
                )
            )
        architectures.append(
            ArchitectureDefinition(
                name=arch["name"], provider="aws", collections=collections, connectors=[]
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


def render_report(resolution: Resolution, source: dict[str, Any] | None = None) -> str:
    names = {a["id"]: a["name"] for a in (source or {}).get("architectures", [])}
    architecture_ids = list(
        dict.fromkeys(
            [m.rule.architecture_id for m in resolution.matches]
            + [o.rule.architecture_id for o in resolution.omissions]
        )
    )
    lines = [
        "# Standard architectures — resolution report",
        "",
        "Generated by `scripts/resolve_standard_architectures.py` — do not edit by hand.",
        "",
        f"Pricing snapshot: `{resolution.snapshot_date}`",
        "",
        "`tiered` marks SKUs with more than one On-Demand price row (usage tiers); the price "
        "lookup uses the first row read (research.md §7.3).",
    ]
    for arch_id in architecture_ids:
        lines += ["", f"## {names.get(arch_id, arch_id)}", ""]
        lines += [
            "| Component | Figure | Region | Service | SKU | Unit | Quantity | Tiered | Note |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for m in resolution.matches:
            if m.rule.architecture_id != arch_id:
                continue
            r = m.rule
            lines.append(
                f"| {r.component_id} | {r.figure} | {r.region} | {m.service_code} | {m.sku} | "
                f"{m.unit} | {r.quantity} | {'yes' if m.tiered else ''} | {r.note or ''} |"
            )
        omitted = [o for o in resolution.omissions if o.rule.architecture_id == arch_id]
        if omitted:
            lines += ["", "**Left out**", "", "| Component | Figure | Reason |", "|---|---|---|"]
            for o in omitted:
                lines.append(f"| {o.rule.component_id} | {o.rule.figure} | {o.reason} |")
    return "\n".join(lines) + "\n"
