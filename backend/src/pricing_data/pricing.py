"""Read-only DuckDB price lookup over `price_fact` (spec FR-010, FR-011, FR-012).

Maps a (sku, pricing_term, purchase_option) pricing input to a real, current price — or
`None` if no matching row exists, which the caller (services/price_calculation.py) must treat
as unpriceable, never estimated (FR-012).
"""

from __future__ import annotations

from collections.abc import Sequence

import duckdb

from src.config import settings
from src.pricing_data.errors import PricingDataUnavailableError
from src.pricing_data.snapshot import resolve_latest_snapshot_date

# The raw AWS price_fact data is inconsistently formatted (e.g. `lease_contract_length` mixes
# "1yr" and "1 yr"; `purchase_option` mixes "NoUpfront" and "No Upfront"), confirmed against
# the real snapshot during implementation. Every comparison below strips whitespace on both
# sides so both forms match.
_TERM_MAP = {
    "on_demand": ("OnDemand", None),
    "reserved_1yr": ("Reserved", "1yr"),
    "reserved_3yr": ("Reserved", "3yr"),
}
_PURCHASE_OPTION_MAP = {
    "not_applicable": None,
    "no_upfront": "NoUpfront",
    "partial_upfront": "PartialUpfront",
    "all_upfront": "AllUpfront",
}


def _price_fact_path(snapshot_date: str) -> str:
    return (
        f"{settings.aws_pricing_parquet_dir}/price_fact/"
        f"snapshot_date={snapshot_date}/region={settings.aws_pricing_region}/part-0.parquet"
    )


def lookup_price(
    *, sku: str, pricing_term: str, purchase_option: str, snapshot_date: str | None = None
) -> float | None:
    """Return the unit price for one SKU/term/purchase_option, or None if not priceable."""
    snapshot_date = snapshot_date or resolve_latest_snapshot_date()
    term, lease_length = _TERM_MAP[pricing_term]
    purchase = _PURCHASE_OPTION_MAP[purchase_option]

    query = "SELECT price FROM read_parquet(?) WHERE sku = ? AND term = ?"
    params: list[object] = [_price_fact_path(snapshot_date), sku, term]
    if lease_length is not None:
        query += " AND REPLACE(lease_contract_length, ' ', '') = ?"
        params.append(lease_length)
    if purchase is not None:
        query += " AND REPLACE(purchase_option, ' ', '') = ?"
        params.append(purchase)
    query += " LIMIT 1"

    try:
        con = duckdb.connect(":memory:", read_only=False)
        row = con.execute(query, params).fetchone()
    except duckdb.Error as exc:
        raise PricingDataUnavailableError(str(exc)) from exc

    return float(row[0]) if row else None


def resolve_units(
    selections: Sequence[tuple[str, str, str]], *, snapshot_date: str | None = None
) -> dict[tuple[str, str, str], str | None]:
    """Batched billing-unit lookup for many (sku, pricing_term, purchase_option) tuples
    (spec FR-004, FR-005).

    One DuckDB query covers every distinct SKU involved; matching against each tuple's
    normalized term/purchase_option happens in Python — the same "resolve once per request,
    not once per row" discipline `lookup_price`'s caller already relies on for price
    (research.md #3), applied here so a whole Architecture's units cost one query, not N.
    `None` for a tuple with no matching `price_fact` row, same condition that makes it
    unpriceable (spec data-model.md).
    """
    if not selections:
        return {}

    snapshot_date = snapshot_date or resolve_latest_snapshot_date()
    skus = sorted({sku for sku, _, _ in selections})
    placeholders = ",".join("?" for _ in skus)

    query = (
        "SELECT sku, term, lease_contract_length, purchase_option, unit "
        f"FROM read_parquet(?) WHERE sku IN ({placeholders})"
    )
    try:
        con = duckdb.connect(":memory:", read_only=False)
        rows = con.execute(query, [_price_fact_path(snapshot_date), *skus]).fetchall()
    except duckdb.Error as exc:
        raise PricingDataUnavailableError(str(exc)) from exc

    # Index by (sku, term, normalized lease, normalized purchase_option) -> unit. When more
    # than one row shares a combo (e.g. Reserved's recurring-rate row vs. its upfront-quantity
    # row both carry the same lease/purchase_option), the FIRST one read wins, so this stays
    # consistent with `lookup_price`'s own unordered `LIMIT 1` over the same unordered scan —
    # both read the same underlying rows in the same physical order, so "first" here picks the
    # same row `lookup_price` would have priced, keeping `unit` truthful about what was priced.
    index: dict[tuple[str, str, str, str], str] = {}
    for sku, term, lease, purchase, unit in rows:
        key = (sku, term, (lease or "").replace(" ", ""), (purchase or "").replace(" ", ""))
        index.setdefault(key, unit)

    result: dict[tuple[str, str, str], str | None] = {}
    for sku, pricing_term, purchase_option in selections:
        term, lease_length = _TERM_MAP[pricing_term]
        purchase = _PURCHASE_OPTION_MAP[purchase_option]
        if lease_length is None:
            # on_demand: no lease/purchase_option to disambiguate — match on sku+term alone.
            unit = next((u for (s, t, _l, _p), u in index.items() if s == sku and t == term), None)
        else:
            key = (sku, term, lease_length, purchase or "")
            unit = index.get(key)
        result[(sku, pricing_term, purchase_option)] = unit
    return result
