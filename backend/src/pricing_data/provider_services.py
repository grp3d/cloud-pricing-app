"""The services in a GCP or Azure pricing snapshot, as the canvas's icon maps see them (020,
research R4/R5), shared by the icon map generator (`scripts/generate_provider_service_icon_map.py`)
and the Admin icon check (027, `icon_coverage.py`), so the two read the same services.

GCP services come from `sku` (each SKU's product taxonomy) joined to `service` (display names); a
service is first-party unless every one of its SKUs sits under a third-party taxonomy group.
Azure services come from `price_item`; the Azure price list has no Marketplace software, so every
Azure service is first-party.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import duckdb

from src.pricing_data.snapshot import ActiveSnapshot

CATEGORY_RULES = Path(__file__).resolve().parent.parent / "db" / "seed" / "service_categories.json"
CATEGORIES = frozenset({"compute", "storage", "database", "networking"})


@dataclass(frozen=True)
class Service:
    service_id: str
    name: str
    # GCP: taxonomy paths (" > "-joined, without "GCP"); Azure: product names.
    families: tuple[str, ...] = ()
    categorized: bool = False
    first_party: bool = True


# GCP top-level taxonomy groups that hold only third-party products.
_GCP_THIRD_PARTY = frozenset({"Marketplace Services", "Third Party Services"})


# --- Categories (the seed rules, applied as the app does) --------------------------------------


def load_category_rules(path: Path = CATEGORY_RULES) -> list[dict]:
    rules = json.loads(path.read_text())["rules"]
    return [r for r in rules if r["category"] in CATEGORIES]


def gcp_categorized(taxonomy: list[str], rules: list[dict]) -> bool:
    """`taxonomy` without its leading "GCP"; level 1 and level 2 rules."""
    levels = {"taxonomy_1": taxonomy[0] if taxonomy else None,
              "taxonomy_2": taxonomy[1] if len(taxonomy) > 1 else None}
    return any(r["provider"] == "gcp" and levels.get(r["match_field"]) == r["match_value"]
               for r in rules)


def azure_categorized(service_family: str, service_name: str, rules: list[dict]) -> bool:
    values = {"service_family": service_family, "service_name": service_name}
    return any(r["provider"] == "azure" and values.get(r["match_field"]) == r["match_value"]
               for r in rules)


# --- Reading the pricing data ------------------------------------------------------------------


def _files(snapshot: ActiveSnapshot, table: str) -> list[str]:
    return [f for region in sorted(snapshot.regions(table)) for f in snapshot.files(table, region)]


def read_services(provider: str, snapshot: ActiveSnapshot,
                  rules: list[dict] | None = None) -> list[Service]:
    """Every service in `snapshot`; `rules` (the category seed rules) set `categorized`."""
    rules = load_category_rules() if rules is None else rules
    con = duckdb.connect(":memory:")
    try:
        if provider == "gcp":
            rows = con.execute(
                "SELECT k.service_id, any_value(s.display_name), "
                "list(DISTINCT array_to_string(k.product_taxonomy[2:], ' > ')), "
                "list(DISTINCT k.product_taxonomy[2:3]) "
                "FROM read_parquet(?) k LEFT JOIN read_parquet(?) s USING (service_id) "
                "GROUP BY 1",
                [_files(snapshot, "sku"), _files(snapshot, "service")],
            ).fetchall()
            return [
                Service(
                    service_id=sid,
                    name=name or sid,
                    families=tuple(sorted(f for f in paths if f)),
                    categorized=any(gcp_categorized(list(levels or []), rules)
                                    for levels in level_lists),
                    first_party=any((levels or [None])[0] not in _GCP_THIRD_PARTY
                                    for levels in level_lists),
                )
                for sid, name, paths, level_lists in rows
            ]
        rows = con.execute(
            "SELECT service_id, any_value(service_name), list(DISTINCT product_name), "
            "list(DISTINCT [service_family, service_name]) "
            "FROM read_parquet(?, union_by_name = true) GROUP BY 1",
            [_files(snapshot, "price_item")],
        ).fetchall()
        return [
            Service(
                service_id=sid,
                name=name or sid,
                families=tuple(sorted(p for p in products if p)),
                categorized=any(azure_categorized(fam or "", svc or "", rules)
                                for fam, svc in pairs),
            )
            for sid, name, products, pairs in rows
        ]
    finally:
        con.close()
