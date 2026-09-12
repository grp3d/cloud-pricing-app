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


class InvalidRegexPatternError(ValueError):
    """Raised when a filter's regex pattern is malformed (008-ui-updates-corrections, US7,
    FR-021, research.md §2). `field` names which of `service_code`/`product_family`/`text`
    the bad pattern came from, so the frontend can show the message inline next to it
    (data-model.md)."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


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


def _validate_regex_pattern(con: duckdb.DuckDBPyConnection, field: str, pattern: str) -> None:
    """Probes `pattern` against an empty string via the real DuckDB/RE2 engine
    (008-ui-updates-corrections, research.md §2) — the authoritative validity check, not an
    approximation via Python's own (differently-syntaxed) `re` module. Raises
    `InvalidRegexPatternError` naming `field` if DuckDB rejects the pattern, so the combined
    query below never runs a filter whose error can't be attributed to one field."""
    try:
        con.execute("SELECT regexp_matches('', ?, 'i')", [pattern])
    except duckdb.Error as exc:
        raise InvalidRegexPatternError(field, str(exc)) from exc


def search_catalog(
    *,
    service_code: str | None = None,
    product_family: str | None = None,
    text: str | None = None,
    from_region_code: str | None = None,
    to_region_code: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], str, int]:
    """Search the AWS pricing catalog. Returns (rows, snapshot_date_used, total).

    Each row: service_code, service_name, product_family, sku, summary, attributes, unit.
    Each filter is a case-insensitive RE2 regex pattern (research.md §2) — an ordinary literal
    string (e.g. "AmazonEC2") is itself a valid regex matching the same substring it always
    did, so existing exact-text searches keep working unchanged. `total` is the true count of
    every matching row (FR-024), independent of `limit`/`offset` (research.md §3) — never
    estimated.

    009-ui-fixes-next-iteration, US9, FR-029/contracts/api.md §2: `from_region_code`/
    `to_region_code` match against `AWSDataTransfer`'s (and only its) `fromRegionCode`/
    `toRegionCode` attributes — additive to the other three filters, AND-combined the same way.
    """
    if not any([service_code, product_family, text, from_region_code, to_region_code]):
        raise EmptyCatalogFilterError(
            "at least one of service_code, product_family, text, from_region_code, or "
            "to_region_code is required"
        )

    snapshot_date = resolve_latest_snapshot_date()

    where = []
    params: list[object] = []
    if service_code:
        where.append("regexp_matches(p.service_code, ?, 'i')")
        params.append(service_code)
    if product_family:
        where.append("regexp_matches(p.product_family, ?, 'i')")
        params.append(product_family)
    if text:
        # 009-ui-fixes-next-iteration, US1, FR-001/research.md §1: matches `p.sku` too, not
        # only `service_name`/`attributes_json` — before this, searching free text for a SKU's
        # own identifier found nothing for that SKU (only other rows that happen to mention it
        # inside their own attributes), so a user with a SKU id in hand had no way to find and
        # select the actual SKU via search.
        where.append(
            "(regexp_matches(s.service_name, ?, 'i') "
            "OR regexp_matches(p.attributes_json, ?, 'i') "
            "OR regexp_matches(p.sku, ?, 'i'))"
        )
        params.extend([text, text, text])
    if from_region_code:
        where.append(
            "regexp_matches(json_extract_string(p.attributes_json, '$.fromRegionCode'), ?, 'i')"
        )
        params.append(from_region_code)
    if to_region_code:
        where.append(
            "regexp_matches(json_extract_string(p.attributes_json, '$.toRegionCode'), ?, 'i')"
        )
        params.append(to_region_code)
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
    count_query = f"""
        SELECT COUNT(*)
        FROM read_parquet(?) p
        JOIN read_parquet(?) s USING (service_code)
        WHERE {where_clause}
    """

    try:
        con = duckdb.connect(":memory:", read_only=False)

        if service_code:
            _validate_regex_pattern(con, "service_code", service_code)
        if product_family:
            _validate_regex_pattern(con, "product_family", product_family)
        if text:
            _validate_regex_pattern(con, "text", text)
        if from_region_code:
            _validate_regex_pattern(con, "from_region_code", from_region_code)
        if to_region_code:
            _validate_regex_pattern(con, "to_region_code", to_region_code)

        product_path = _product_dim_path(snapshot_date)
        service_path = _service_dim_path(snapshot_date)

        total = con.execute(count_query, [product_path, service_path, *params]).fetchone()[0]
        rows = con.execute(
            query, [product_path, service_path, *params, limit, offset]
        ).fetchall()
        columns = [d[0] for d in con.description]
    except InvalidRegexPatternError:
        raise
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

    return results, snapshot_date, total


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
