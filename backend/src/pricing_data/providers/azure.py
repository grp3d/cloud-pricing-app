"""The Azure adapter (019, research R3 to R8), over the pipeline's `price_item` and
`price_item_savings_plan` tables (pipeline 004 data-model).

- **Item**: `<sku_id>/<meter_id>`, one meter of one Azure SKU (research R4); `service_code` is
  `service_id`. The catalog lists `Consumption` meters; a meter's reservation and savings-plan
  prices are price types of the same item.
- **Location**: a region's files plus `global`'s (research R5). Geography partitions
  (`north-america`, …) are never selectable and never read.
- **Price types** (research R6): `on_demand` = `Consumption`; `reserved_*` = `Reservation` rows of
  the same meter and region by `reservation_term`; `savings_plan_*` = `price_item_savings_plan`
  rows of the item's `Consumption` rows by `term`. `DevTestConsumption` is never used.
- **Reservation**: `unit_price` is the whole term's price, so it is priced like AWS all-upfront:
  an upfront fee and no recurring rate.
- **Units** (research R7): `unit_of_measure` → (block size, base unit); rates are per base unit.
- **`azure_vm`** options pick the Linux or Windows meter of the same VM size: the Windows product
  is the Linux product's name plus ` Windows`, with the same `arm_sku_name` and `sku_name`
  (which excludes Spot and Low Priority, whose `sku_name` carries the suffix).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import Decimal

from src.pricing_data.duckdb_conn import connect
from src.pricing_data.providers._sql import check_patterns, open_views
from src.pricing_data.providers.base import CatalogItem, PriceQuote, Tier
from src.pricing_data.providers.comparable import ComparableMixin, first_nonzero
from src.pricing_data.providers.units import parse_azure_unit
from src.pricing_data.snapshot import GLOBAL, ActiveSnapshot
from src.services.categories import service_key

_TABLES = ("price_item", "price_item_savings_plan")
_WINDOWS = " Windows"

# Catalog `kind` presets: the reference-lookup filters of the pipeline 004 storage layout.
KIND_FILTERS: dict[str, str] = {
    "vm": (
        "service_name = 'Virtual Machines' AND NOT ends_with(product_name, ' Windows') "
        "AND sku_name NOT ILIKE '%Spot%' AND sku_name NOT ILIKE '%Low Priority%'"
    ),
    "block_storage": "service_name = 'Storage' AND product_name ILIKE '%Managed Disks%'",
    "object_storage": (
        "product_name = 'General Block Blob v2' AND ends_with(meter_name, 'Data Stored')"
    ),
    "data_transfer": (
        "service_name = 'Bandwidth' AND product_name IN "
        "('Rtn Preference: MGN', 'Bandwidth - Routing Preference: Internet') "
        "AND meter_name = 'Standard Data Transfer Out'"
    ),
    "managed_db": "service_family = 'Databases'",
}

_RESERVATION_TERMS = {"reserved_1yr": "1 Year", "reserved_3yr": "3 Years"}
_SAVINGS_PLAN_TERMS = {"savings_plan_1yr": "1 Year", "savings_plan_3yr": "3 Years"}

_display_names: dict[ActiveSnapshot, dict[str, str]] = {}


def split_item(item: str) -> tuple[str, str] | None:
    """`<sku_id>/<meter_id>` → (sku_id, meter_id). An Azure `sku_id` itself holds a slash
    (`DZH318Z08M9W/004T`), so the meter is after the last one."""
    sku_id, sep, meter_id = item.rpartition("/")
    if not sep or not sku_id or not meter_id:
        return None
    return sku_id, meter_id


def is_geography(location: str) -> bool:
    """Azure region names (`armRegionName`) never contain a hyphen; the pipeline's geography
    partitions (`north-america`, …) always do (storage layout)."""
    return "-" in location


def _kind_case() -> str:
    whens = " ".join(f"WHEN {cond} THEN '{kind}'" for kind, cond in KIND_FILTERS.items())
    return f"CASE {whens} ELSE NULL END"


# One row per item (`location`, `sku_id`, `meter_id`) of the filtered `Consumption` meters, with
# its published price types. Duplicate-name meters (research R8) collapse into one item.
_ITEMS_SQL = """
WITH consumption AS (
    SELECT location, sku_id, meter_id, service_id, service_name, service_family, product_name,
        sku_name, arm_sku_name, meter_name, unit_of_measure, location_display_name,
        price_item_key
    FROM price_item
    WHERE price_type = 'Consumption' AND location = ANY(?) AND ({where})
),
items AS (
    SELECT location, sku_id, meter_id,
        min(service_id) AS service_id, min(service_name) AS service_name,
        min(service_family) AS service_family, min(product_name) AS product_name,
        min(sku_name) AS sku_name, min(arm_sku_name) AS arm_sku_name,
        min(meter_name) AS meter_name, min(unit_of_measure) AS unit_of_measure,
        min(location_display_name) AS location_display_name,
        list(price_item_key) AS keys, min(kind) AS kind
    FROM (SELECT *, {kind_case} AS kind FROM consumption)
    GROUP BY location, sku_id, meter_id
)
SELECT i.*,
    EXISTS (SELECT 1 FROM price_item r WHERE r.price_type = 'Reservation'
            AND r.meter_id = i.meter_id AND r.location = i.location
            AND r.reservation_term = '1 Year') AS r1,
    EXISTS (SELECT 1 FROM price_item r WHERE r.price_type = 'Reservation'
            AND r.meter_id = i.meter_id AND r.location = i.location
            AND r.reservation_term = '3 Years') AS r3,
    EXISTS (SELECT 1 FROM price_item_savings_plan s
            WHERE list_contains(i.keys, s.price_item_key) AND s.term = '1 Year') AS sp1,
    EXISTS (SELECT 1 FROM price_item_savings_plan s
            WHERE list_contains(i.keys, s.price_item_key) AND s.term = '3 Years') AS sp3,
    count(*) OVER () AS total
FROM items i
ORDER BY i.product_name, i.sku_name, i.meter_name, i.sku_id, i.meter_id
LIMIT ? OFFSET ?
"""


class AzureProvider(ComparableMixin):
    code = "azure"
    reports_price_types = True

    # --- locations ---------------------------------------------------------------------------

    def locations(self, snapshot: ActiveSnapshot) -> list[str]:
        return [
            loc for loc in snapshot.locations() if loc != GLOBAL and not is_geography(loc)
        ]

    def display_names(self, snapshot: ActiveSnapshot) -> dict[str, str]:
        """Each selectable region's `location_display_name` (e.g. `eastus` → `US East`), read
        once per snapshot."""
        cached = _display_names.get(snapshot)
        if cached is not None:
            return cached
        names: dict[str, str] = {}
        for loc in self.locations(snapshot):
            files = snapshot.files("price_item", loc)
            if not files:
                continue
            with connect() as con:
                row = con.execute(
                    "SELECT location_display_name FROM read_parquet(?) "
                    "WHERE location_display_name <> '' LIMIT 1",
                    [files],
                ).fetchone()
            if row and row[0]:
                names[loc] = row[0]
        _display_names.clear()
        _display_names[snapshot] = names
        return names

    # --- catalog -----------------------------------------------------------------------------

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
        con = open_views(snapshot, region, _TABLES, required="price_item")
        try:
            check_patterns(con, patterns or {})
            sql = _ITEMS_SQL.format(where=" AND ".join(where) or "true", kind_case=_kind_case())
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
        """`filters`: `text`, `service_code` (`service_id` or `service_name`),
        `product_family` (`product_name`), `kind`. Text filters are case-insensitive RE2
        patterns, as for AWS."""
        where: list[str] = []
        params: list[object] = []
        text = filters.get("text")
        service_code = filters.get("service_code")
        product_family = filters.get("product_family")
        kind = filters.get("kind")
        if text:
            where.append(
                "regexp_matches(concat_ws(' ', service_name, product_name, sku_name, "
                "arm_sku_name, meter_name, sku_id, meter_id), ?, 'i')"
            )
            params.append(text)
        if service_code:
            where.append(
                "(regexp_matches(service_id, ?, 'i') OR regexp_matches(service_name, ?, 'i'))"
            )
            params.extend([service_code, service_code])
        if product_family:
            where.append("regexp_matches(product_name, ?, 'i')")
            params.append(product_family)
        if kind:
            where.append(f"({KIND_FILTERS[str(kind)]})")
        return self._query(
            snapshot, region=region, where=where, params=params, limit=limit, offset=offset,
            patterns={"text": text, "service_code": service_code,
                      "product_family": product_family},
        )

    def describe(
        self, snapshot: ActiveSnapshot, items: Sequence[tuple[str, str]], *, region: str
    ) -> dict[tuple[str, str], CatalogItem]:
        pairs = [(code, split_item(item)) for code, item in items]
        refs = sorted({f"{p[0]}|{p[1]}" for _code, p in pairs if p is not None})
        if not refs:
            return {}
        found, _total = self._query(
            snapshot, region=region,
            where=["list_contains(?, sku_id || '|' || meter_id)"], params=[refs],
            limit=len(refs) * 2 + 1, offset=0,
        )
        by_key = {(i.service_code, i.sku): i for i in found}
        return {key: by_key[key] for key in items if key in by_key}

    def exists(
        self, snapshot: ActiveSnapshot, items: Iterable[tuple[str, str]], *, region: str
    ) -> set[tuple[str, str]]:
        return set(self.describe(snapshot, list(items), region=region))

    def units(
        self, snapshot: ActiveSnapshot, keys: Sequence[tuple[str, str, str]], *, region: str
    ) -> dict[tuple[str, str, str], str | None]:
        details = self._by_item(snapshot, [k[0] for k in keys], region=region)
        return {k: details[k[0]].unit for k in keys if k[0] in details}

    def _by_item(
        self, snapshot: ActiveSnapshot, items: Sequence[str], *, region: str
    ) -> dict[str, CatalogItem]:
        refs = sorted({f"{p[0]}|{p[1]}" for p in map(split_item, items) if p is not None})
        if not refs:
            return {}
        found, _total = self._query(
            snapshot, region=region,
            where=["list_contains(?, sku_id || '|' || meter_id)"], params=[refs],
            limit=len(refs) * 2 + 1, offset=0,
        )
        return {i.sku: i for i in found}

    # --- prices ------------------------------------------------------------------------------

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
        ref = split_item(item)
        if ref is None or purchase_option != "not_applicable":
            return None
        con = open_views(snapshot, region, _TABLES, required="price_item")
        try:
            meter = _consumption_rows(con, region, *ref)
            if not meter:
                return None
            if options and options.get("kind") == "azure_vm":
                meter = _os_meter(con, region, meter[0], options.get("os"))
                if not meter:
                    return None
            first = meter[0]
            unit = parse_azure_unit(first["unit_of_measure"])
            if pricing_term == "on_demand":
                tiers = [_tier(r["tier_minimum_units"], r["unit_price"], unit.multiplier)
                         for r in meter]
                return PriceQuote(unit=first["unit_of_measure"], tiers=tiers,
                                  unit_class=unit.classification)
            if pricing_term in _SAVINGS_PLAN_TERMS:
                rows = con.execute(
                    "SELECT p.tier_minimum_units, s.unit_price FROM price_item p "
                    "JOIN price_item_savings_plan s ON s.price_item_key = p.price_item_key "
                    "AND s.location = p.location "
                    "WHERE p.location = ? AND p.sku_id = ? AND p.meter_id = ? "
                    "AND p.price_type = 'Consumption' AND s.term = ?",
                    [first["location"], first["sku_id"], first["meter_id"],
                     _SAVINGS_PLAN_TERMS[pricing_term]],
                ).fetchall()
                if not rows:
                    return None
                return PriceQuote(
                    unit=first["unit_of_measure"],
                    tiers=[_tier(start, price, unit.multiplier) for start, price in rows],
                    unit_class=unit.classification,
                )
            if pricing_term in _RESERVATION_TERMS:
                prices = {
                    r[0] for r in con.execute(
                        "SELECT unit_price FROM price_item WHERE location = ? AND meter_id = ? "
                        "AND price_type = 'Reservation' AND reservation_term = ?",
                        [first["location"], first["meter_id"], _RESERVATION_TERMS[pricing_term]],
                    ).fetchall()
                }
                if len(prices) != 1 or None in prices:
                    # Not published, or two term prices that can't be told apart (FR-007).
                    return None
                return PriceQuote(
                    unit=first["unit_of_measure"],
                    recurring_rate=Decimal(0),
                    upfront_fee=Decimal(str(prices.pop())),
                )
            return None
        finally:
            con.close()

    def service_key(self, item: CatalogItem) -> str:
        """`service_family|service_name` (research R9)."""
        return service_key(item.attributes.get("service_family"), item.service_name)

    # Trends (research R10): `Consumption` meters per location (geographies left out), the
    # first non-zero tier by `tier_minimum_units`, as published.
    comparable_tables = ("price_item",)

    def _comparable_sql(self) -> str:
        return f"""
            SELECT location, sku_id || '/' || meter_id AS item_key,
                coalesce(min(service_family), '') || '|' || coalesce(min(service_name), '')
                    AS service_key,
                min(service_name) AS service_name,
                concat_ws(' ', min(product_name), min(sku_name), min(meter_name))
                    AS description,
                min(unit_of_measure) AS unit,
                {first_nonzero("unit_price", "tier_minimum_units")} AS price,
                count(DISTINCT tier_minimum_units) > 1 AS tiered
            FROM price_item
            WHERE price_type = 'Consumption' AND location NOT LIKE '%-%'
            GROUP BY location, sku_id, meter_id
        """


def _tier(start: float | None, price: float | None, multiplier: Decimal) -> Tier:
    rate = None if price is None else Decimal(str(price)) / multiplier
    return Tier(Decimal(str(start or 0)), rate)


def _rows(con, sql: str, params: list[object]) -> list[dict]:
    cursor = con.execute(sql, params)
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, r, strict=True)) for r in cursor.fetchall()]


_ROW_COLUMNS = (
    "location, sku_id, meter_id, product_name, sku_name, arm_sku_name, unit_of_measure, "
    "tier_minimum_units, unit_price, price_item_key"
)


def _consumption_rows(con, region: str, sku_id: str, meter_id: str) -> list[dict]:
    """The item's `Consumption` rows (one per tier) in the region or `global`."""
    return _rows(
        con,
        f"SELECT {_ROW_COLUMNS} FROM price_item WHERE location IN (?, ?) AND sku_id = ? AND meter_id = ? "
        "AND price_type = 'Consumption' ORDER BY tier_minimum_units",
        [region, GLOBAL, sku_id, meter_id],
    )


def _os_meter(con, region: str, row: dict, os: str | None) -> list[dict]:
    """The same VM size's meter for `os` (`linux` or `windows`)."""
    base = row["product_name"].removesuffix(_WINDOWS)
    product = base + _WINDOWS if os == "windows" else base
    if product == row["product_name"]:
        return _consumption_rows(con, region, row["sku_id"], row["meter_id"])
    return _rows(
        con,
        f"SELECT {_ROW_COLUMNS} FROM price_item WHERE location = ? AND product_name = ? AND arm_sku_name = ? "
        "AND sku_name = ? AND price_type = 'Consumption' ORDER BY tier_minimum_units",
        [row["location"], product, row["arm_sku_name"], row["sku_name"]],
    )


def _item(row: dict) -> CatalogItem:
    price_types = ["on_demand"]
    for flag, term in (("r1", "reserved_1yr"), ("r3", "reserved_3yr"),
                       ("sp1", "savings_plan_1yr"), ("sp3", "savings_plan_3yr")):
        if row[flag]:
            price_types.append(term)
    summary = " ".join(x for x in (row["product_name"], row["sku_name"], row["meter_name"]) if x)
    attributes = {
        "service_family": row["service_family"] or "",
        "product_name": row["product_name"] or "",
        "sku_name": row["sku_name"] or "",
        "arm_sku_name": row["arm_sku_name"] or "",
        "meter_name": row["meter_name"] or "",
        "unit_of_measure": row["unit_of_measure"] or "",
        "location": row["location"],
    }
    return CatalogItem(
        provider="azure",
        service_code=row["service_id"],
        service_name=row["service_name"],
        product_family=row["product_name"],
        sku=f"{row['sku_id']}/{row['meter_id']}",
        summary=summary,
        attributes={k: v for k, v in attributes.items() if v},
        unit=row["unit_of_measure"],
        location_scope="global" if row["location"] == GLOBAL else "regional",
        kind=row["kind"],
        price_types=tuple(price_types),
    )
