"""Read-only DuckDB catalog search over the AWS pricing Parquet data (spec FR-005).

v1 filtering is limited to service_code, product_family, and free text (spec Assumptions) —
attribute-level faceting (instance type, OS, ...) is deferred. Filters combine with AND; at
least one filter is required to avoid returning the full ~173k-row catalog per region/snapshot.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import duckdb

from src.config import settings
from src.pricing_data.errors import PricingDataUnavailableError
from src.pricing_data.pricing import resolve_units
from src.pricing_data.snapshot import resolve_latest_snapshot_date


class EmptyCatalogFilterError(ValueError):
    """Raised when a catalog search is attempted with no filter at all."""


def parse_attributes(raw: str | None) -> dict[str, str]:
    """Parse `product_dim.attributes_json` into a plain string map (spec FR-001, FR-002).

    Never raises: `None`, empty, or malformed JSON all resolve to `{}` rather than fabricating
    or guessing a value (spec FR-003, Constitution Principle I).
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(value) for key, value in parsed.items()}


def _product_dim_path(snapshot_date: str) -> str:
    return (
        f"{settings.aws_pricing_parquet_dir}/product_dim/"
        f"snapshot_date={snapshot_date}/region={settings.aws_pricing_region}/part-0.parquet"
    )


def _service_dim_path(snapshot_date: str) -> str:
    return (
        f"{settings.aws_pricing_parquet_dir}/service_dim/"
        f"snapshot_date={snapshot_date}/region={settings.aws_pricing_region}/part-0.parquet"
    )


def search_catalog(
    *,
    service_code: str | None = None,
    product_family: str | None = None,
    text: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], str]:
    """Search the AWS pricing catalog. Returns (rows, snapshot_date_used).

    Each row: service_code, service_name, product_family, sku, summary, attributes, unit.
    """
    if not any([service_code, product_family, text]):
        raise EmptyCatalogFilterError(
            "at least one of service_code, product_family, or text is required"
        )

    snapshot_date = resolve_latest_snapshot_date()

    where = []
    params: list[object] = []
    if service_code:
        where.append("p.service_code = ?")
        params.append(service_code)
    if product_family:
        where.append("p.product_family = ?")
        params.append(product_family)
    if text:
        where.append("(s.service_name ILIKE ? OR p.attributes_json ILIKE ?)")
        params.extend([f"%{text}%", f"%{text}%"])
    where_clause = " AND ".join(where)

    query = f"""
        SELECT
            p.service_code,
            s.service_name,
            p.product_family,
            p.sku,
            COALESCE(
                json_extract_string(p.attributes_json, '$.instanceType'),
                p.product_family
            ) AS summary,
            p.attributes_json
        FROM read_parquet(?) p
        JOIN read_parquet(?) s USING (service_code)
        WHERE {where_clause}
        ORDER BY p.service_code, p.sku
        LIMIT ? OFFSET ?
    """

    try:
        con = duckdb.connect(":memory:", read_only=False)
        rows = con.execute(
            query,
            [
                _product_dim_path(snapshot_date),
                _service_dim_path(snapshot_date),
                *params,
                limit,
                offset,
            ],
        ).fetchall()
        columns = [d[0] for d in con.description]
    except duckdb.Error as exc:
        raise PricingDataUnavailableError(str(exc)) from exc

    results = [dict(zip(columns, row, strict=True)) for row in rows]

    # Attach attributes (parsed, never raw JSON) and unit — one batched DuckDB lookup for
    # every result's unit rather than one query per row (research.md #3).
    units = resolve_units(
        [(r["sku"], "on_demand", "not_applicable") for r in results],
        snapshot_date=snapshot_date,
    )
    for result in results:
        raw_attributes = result.pop("attributes_json")
        result["attributes"] = parse_attributes(raw_attributes)
        result["unit"] = units.get((result["sku"], "on_demand", "not_applicable"))

    return results, snapshot_date


def resolve_attributes(
    skus: Sequence[tuple[str, str]], *, snapshot_date: str | None = None
) -> dict[tuple[str, str], dict[str, str]]:
    """Batched `attributes` lookup for many (service_code, sku) pairs (004, FR-014,
    research.md #5) — one DuckDB query for the whole set, mirroring `resolve_units`'s (003)
    "resolve once per request" discipline rather than one query per SKU Selection. `{}` for any
    pair with no matching row, same as `parse_attributes`'s missing-data behavior.
    """
    if not skus:
        return {}

    snapshot_date = snapshot_date or resolve_latest_snapshot_date()
    unique_skus = sorted({sku for _, sku in skus})
    placeholders = ",".join("?" for _ in unique_skus)

    query = (
        "SELECT service_code, sku, attributes_json "
        f"FROM read_parquet(?) WHERE sku IN ({placeholders})"
    )
    try:
        con = duckdb.connect(":memory:", read_only=False)
        rows = con.execute(query, [_product_dim_path(snapshot_date), *unique_skus]).fetchall()
    except duckdb.Error as exc:
        raise PricingDataUnavailableError(str(exc)) from exc

    index: dict[tuple[str, str], dict[str, str]] = {
        (service_code, sku): parse_attributes(raw) for service_code, sku, raw in rows
    }
    return {key: index.get(key, {}) for key in skus}
