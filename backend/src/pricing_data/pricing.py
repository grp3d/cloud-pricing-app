"""Read-only DuckDB price lookup over `price_fact` (spec FR-010, FR-011, FR-012).

Maps a (sku, pricing_term, purchase_option) pricing input to a real, current price — or
`None` if no matching row exists, which the caller (services/price_calculation.py) must treat
as unpriceable, never estimated (FR-012).
"""

from __future__ import annotations

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
