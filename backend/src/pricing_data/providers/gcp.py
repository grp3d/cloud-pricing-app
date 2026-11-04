"""The GCP adapter (019, research R3 to R8), over the pipeline's `service`, `sku`, `sku_price`
and `sku_price_tier` tables (pipeline 004 data-model).

- **Item**: the `sku_id`; `service_code` is the `service_id` (research R4).
- **Location**: a region's files plus `global`'s (research R5). A multi-regional SKU is filed
  under each member region, so it appears once in a region. `service` is only in `global`.
- **Price types** (research R6): `on_demand` = consumption model `Default`; `commitment_1yr` /
  `commitment_3yr` = the models described `… CUD - 1 Year` / `… CUD - 3 Year`. A SKU with two
  different matching commitment models can't be told apart, so it is unpriced (FR-007).
- **Tiers**: `sku_price_tier.start_amount`; the rate is `list_price ÷ unit_quantity`
  (research R7, R8). A null `list_price` is "not published", never 0.
- **`gcp_machine`** options price a machine as vCPUs × the core SKU's rate plus GiB × the RAM
  SKU's rate, both hourly, shown as two components (research R6).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import Decimal

from src.pricing_data.providers._sql import check_patterns, open_views
from src.pricing_data.providers.base import (
    CatalogItem,
    ComparablePrice,
    PriceComponent,
    PriceQuote,
    Tier,
)
from src.pricing_data.providers.units import parse_gcp_unit
from src.pricing_data.snapshot import GLOBAL, ActiveSnapshot

_TABLES = ("service", "sku", "sku_price", "sku_price_tier")

_TAXONOMY = "array_to_string(product_taxonomy[2:], ' > ')"

# Catalog `kind` presets: the reference-lookup filters of the pipeline 004 storage layout. The
# `vm` kind lists predefined machine-family cores; each carries its RAM SKU (`ram_sku`).
KIND_FILTERS: dict[str, str] = {
    "vm": (
        "list_contains(product_taxonomy, 'VMs On Demand') "
        "AND regexp_matches(display_name, '^[A-Z0-9]+ Instance Core running in ')"
    ),
    "block_storage": (
        "list_contains(product_taxonomy, 'Persistent Disk') "
        "AND list_contains(product_taxonomy, 'Capacity')"
    ),
    "object_storage": "product_taxonomy[3] = 'GCS' AND product_taxonomy[4] = 'Storage'",
    "data_transfer": (
        "product_taxonomy[2] = 'Network' AND product_taxonomy[3] = 'Egress' "
        "AND product_taxonomy[4] = 'GCE'"
    ),
    "managed_db": "product_taxonomy[2] = 'Databases'",
}

_SCOPES = {"TYPE_GLOBAL": "global", "TYPE_MULTI_REGIONAL": "multi_regional"}
_COMMITMENTS = {"commitment_1yr": "% CUD - 1 Year", "commitment_3yr": "% CUD - 3 Year"}


def _kind_case() -> str:
    whens = " ".join(f"WHEN {cond} THEN '{kind}'" for kind, cond in KIND_FILTERS.items())
    return f"CASE {whens} ELSE NULL END"


_ITEMS_SQL = """
WITH located AS (
    SELECT sku_id, location, service_id, display_name, product_taxonomy, geo_taxonomy_type,
        {kind_case} AS kind,
        row_number() OVER (PARTITION BY sku_id ORDER BY location = 'global') AS pick
    FROM sku
    WHERE location = ANY(?) AND ({where})
),
items AS (SELECT * EXCLUDE (pick) FROM located WHERE pick = 1),
prices AS (
    SELECT p.sku_id, p.location,
        bool_or(p.consumption_model_description = 'Default') AS od,
        bool_or(p.consumption_model_description LIKE '% CUD - 1 Year') AS c1,
        bool_or(p.consumption_model_description LIKE '% CUD - 3 Year') AS c3,
        min(p.unit) FILTER (WHERE p.consumption_model_description = 'Default') AS od_unit,
        min(p.unit) AS any_unit
    FROM sku_price p JOIN items i ON i.sku_id = p.sku_id AND i.location = p.location
    GROUP BY p.sku_id, p.location
)
SELECT i.*, coalesce(s.display_name, '') AS service_name, {taxonomy} AS taxonomy,
    coalesce(pr.od, false) AS od, coalesce(pr.c1, false) AS c1, coalesce(pr.c3, false) AS c3,
    coalesce(pr.od_unit, pr.any_unit) AS unit,
    (SELECT r.sku_id FROM sku r
     WHERE i.kind = 'vm' AND r.location = i.location
       AND r.display_name = replace(i.display_name, ' Instance Core ', ' Instance Ram ')
     LIMIT 1) AS ram_sku,
    count(*) OVER () AS total
FROM items i
LEFT JOIN service s ON s.service_id = i.service_id
LEFT JOIN prices pr ON pr.sku_id = i.sku_id AND pr.location = i.location
ORDER BY i.display_name, i.sku_id
LIMIT ? OFFSET ?
"""


class GcpProvider:
    code = "gcp"
    reports_price_types = True

    def locations(self, snapshot: ActiveSnapshot) -> list[str]:
        return [loc for loc in snapshot.locations() if loc != GLOBAL]

    def display_names(self, snapshot: ActiveSnapshot) -> dict[str, str]:
        """GCP publishes no region display names; the code is the name."""
        return {}

    def _query(
        self,
        snapshot: ActiveSnapshot,
        *,
        region: str,
        where: list[str],
        params: list[object],
        limit: int,
        offset: int,
        patterns: dict[str, str | None] | None = None,
    ) -> tuple[list[CatalogItem], int]:
        con = open_views(snapshot, region, _TABLES, required="sku")
        try:
            check_patterns(con, patterns or {})
            sql = _ITEMS_SQL.format(
                where=" AND ".join(where) or "true", kind_case=_kind_case(), taxonomy=_TAXONOMY
            )
            cursor = con.execute(sql, [[region, GLOBAL], *params, limit, offset])
            columns = [d[0] for d in cursor.description]
            rows = [dict(zip(columns, r, strict=True)) for r in cursor.fetchall()]
        finally:
            con.close()
        total = rows[0]["total"] if rows else 0
        return [_item(r) for r in rows], total

    def search(
        self, snapshot: ActiveSnapshot, *, region: str, limit: int, offset: int, **filters: object
    ) -> tuple[list[CatalogItem], int]:
        """`filters`: `text`, `service_code` (`service_id` or service name), `product_family`
        (the taxonomy path), `kind`. Text filters are case-insensitive RE2 patterns."""
        where: list[str] = []
        params: list[object] = []
        text = filters.get("text")
        service_code = filters.get("service_code")
        product_family = filters.get("product_family")
        kind = filters.get("kind")
        if text:
            where.append(
                f"regexp_matches(concat_ws(' ', display_name, sku_id, {_TAXONOMY}), ?, 'i')"
            )
            params.append(text)
        if service_code:
            where.append(
                "(regexp_matches(service_id, ?, 'i') OR service_id IN "
                "(SELECT service_id FROM service WHERE regexp_matches(display_name, ?, 'i')))"
            )
            params.extend([service_code, service_code])
        if product_family:
            where.append(f"regexp_matches({_TAXONOMY}, ?, 'i')")
            params.append(product_family)
        if kind:
            where.append(f"({KIND_FILTERS[str(kind)]})")
        return self._query(
            snapshot, region=region, where=where, params=params, limit=limit, offset=offset,
            patterns={"text": text, "service_code": service_code,
                      "product_family": product_family},
        )

    def _by_item(
        self, snapshot: ActiveSnapshot, items: Sequence[str], *, region: str
    ) -> dict[str, CatalogItem]:
        refs = sorted(set(items))
        if not refs:
            return {}
        found, _total = self._query(
            snapshot, region=region, where=["list_contains(?, sku_id)"], params=[refs],
            limit=len(refs) + 1, offset=0,
        )
        return {i.sku: i for i in found}

    def describe(
        self, snapshot: ActiveSnapshot, items: Sequence[tuple[str, str]], *, region: str
    ) -> dict[tuple[str, str], CatalogItem]:
        by_sku = self._by_item(snapshot, [item for _code, item in items], region=region)
        return {
            (code, item): by_sku[item]
            for code, item in items
            if item in by_sku and by_sku[item].service_code == code
        }

    def exists(
        self, snapshot: ActiveSnapshot, items: Iterable[tuple[str, str]], *, region: str
    ) -> set[tuple[str, str]]:
        return set(self.describe(snapshot, list(items), region=region))

    def units(
        self, snapshot: ActiveSnapshot, keys: Sequence[tuple[str, str, str]], *, region: str
    ) -> dict[tuple[str, str, str], str | None]:
        details = self._by_item(snapshot, [k[0] for k in keys], region=region)
        return {k: details[k[0]].unit for k in keys if k[0] in details}

    def price(
        self,
        snapshot: ActiveSnapshot,
        *,
        item: str,
        pricing_term: str,
        purchase_option: str,
        region: str,
        options: dict | None = None,
    ) -> PriceQuote | None:
        if purchase_option != "not_applicable":
            return None
        if pricing_term == "on_demand":
            model = ("=", "Default")
        elif pricing_term in _COMMITMENTS:
            model = ("LIKE", _COMMITMENTS[pricing_term])
        else:
            return None
        con = open_views(snapshot, region, _TABLES, required="sku")
        try:
            if options and options.get("kind") == "gcp_machine":
                return _machine_quote(con, region, item, model, options)
            return _sku_quote(con, region, item, model)
        finally:
            con.close()

    def service_key(self, item: CatalogItem) -> str:
        raise NotImplementedError("service categories arrive with Trends (US2)")

    def comparable_prices(self, snapshot: ActiveSnapshot) -> list[ComparablePrice]:
        raise NotImplementedError("comparable_prices arrives with Trends (US2)")


def _sku_quote(con, region: str, sku_id: str, model: tuple[str, str]) -> PriceQuote | None:
    op, value = model
    prices = con.execute(
        "SELECT location, consumption_model, unit, unit_quantity FROM sku_price "
        f"WHERE location IN (?, ?) AND sku_id = ? AND consumption_model_description {op} ? "
        "ORDER BY location = 'global'",
        [region, GLOBAL, sku_id, value],
    ).fetchall()
    if not prices:
        return None
    location = prices[0][0]
    models = {p[1] for p in prices if p[0] == location}
    if len(models) != 1:
        # Two commitment models for one SKU: the right one can't be told (FR-007).
        return None
    _loc, consumption_model, unit, unit_quantity = prices[0]
    parsed = parse_gcp_unit(unit, unit_quantity)
    rows = con.execute(
        "SELECT start_amount, list_price FROM sku_price_tier "
        "WHERE location = ? AND sku_id = ? AND consumption_model = ? ORDER BY start_amount",
        [location, sku_id, consumption_model],
    ).fetchall()
    if not rows:
        return None
    tiers = [
        Tier(Decimal(start or 0), None if price is None else Decimal(price) / parsed.multiplier)
        for start, price in rows
    ]
    return PriceQuote(unit=unit, tiers=tiers, unit_class=parsed.classification)


def _machine_quote(
    con, region: str, core_sku: str, model: tuple[str, str], options: dict
) -> PriceQuote | None:
    """vCPUs × core rate + GiB × RAM rate, per hour (research R6)."""
    core = _sku_quote(con, region, core_sku, model)
    ram = _sku_quote(con, region, str(options.get("ram_sku") or ""), model)
    if core is None or ram is None or len(core.tiers) != 1 or len(ram.tiers) != 1:
        return None
    if core.unit != "h" or ram.unit != "GiBy.h":
        return None
    core_rate, ram_rate = core.tiers[0].rate, ram.tiers[0].rate
    if core_rate is None or ram_rate is None:
        return None
    vcpus = Decimal(str(options["vcpus"]))
    memory = Decimal(str(options["memory_gib"]))
    components = (
        PriceComponent("vCPUs", core_sku, vcpus, core_rate),
        PriceComponent("Memory (GiB)", str(options["ram_sku"]), memory, ram_rate),
    )
    rate = vcpus * core_rate + memory * ram_rate
    return PriceQuote(
        unit="h", tiers=[Tier(Decimal(0), rate)], unit_class=core.unit_class,
        components=components,
    )


def _item(row: dict) -> CatalogItem:
    price_types = [t for flag, t in (("od", "on_demand"), ("c1", "commitment_1yr"),
                                     ("c3", "commitment_3yr")) if row[flag]]
    attributes = {
        "geo_taxonomy_type": row["geo_taxonomy_type"] or "",
        "location": row["location"],
        "ram_sku": row["ram_sku"] or "",
    }
    return CatalogItem(
        provider="gcp",
        service_code=row["service_id"],
        service_name=row["service_name"] or None,
        product_family=row["taxonomy"],
        sku=row["sku_id"],
        summary=row["display_name"] or "",
        attributes={k: v for k, v in attributes.items() if v},
        unit=row["unit"],
        location_scope=_SCOPES.get(row["geo_taxonomy_type"], "regional"),
        kind=row["kind"],
        price_types=tuple(price_types),
    )
