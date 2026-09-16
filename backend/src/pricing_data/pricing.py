"""Read-only DuckDB price lookup over `price_fact` (spec FR-010, FR-011, FR-012;
006-fix-reserved-pricing FR-001-FR-005).

Maps a (sku, pricing_term, purchase_option) pricing input to a real, current price — or
`None` if no matching row exists, which the caller (services/price_calculation.py) must treat
as unpriceable, never estimated (FR-012). `lookup_reserved_price` is the Reserved-term
counterpart of `lookup_price`: a Reserved/Partial-or-All-Upfront combination has two distinct
`price_fact` rows (a recurring `Hrs` rate and a one-time `Quantity` upfront fee) sharing every
other column, which `lookup_price`'s single-row `LIMIT 1` can't return both of at once (006,
FR-004) — the actual bug this module's second function exists to fix.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

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


def _price_fact_path(snapshot_date: str, region: str) -> str:
    return (
        f"{settings.aws_pricing_parquet_dir}/price_fact/"
        f"snapshot_date={snapshot_date}/region={region}/part-0.parquet"
    )


def lookup_price(
    *,
    sku: str,
    pricing_term: str,
    purchase_option: str,
    region: str,
    snapshot_date: str | None = None,
) -> float | None:
    """Return the unit price for one SKU/term/purchase_option in `region`, or None if not
    priceable (010-multi-region-support, spec FR-005 — every lookup is now scoped to the
    caller-supplied region rather than one global default)."""
    snapshot_date = snapshot_date or resolve_latest_snapshot_date()
    term, lease_length = _TERM_MAP[pricing_term]
    purchase = _PURCHASE_OPTION_MAP[purchase_option]

    query = "SELECT price FROM read_parquet(?) WHERE sku = ? AND term = ?"
    params: list[object] = [_price_fact_path(snapshot_date, region), sku, term]
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


@dataclass(frozen=True)
class ReservedPrice:
    """Both `price_fact` values a Reserved-term selection's cost needs (006, FR-001/FR-002).
    Not persisted — an in-memory result of `lookup_reserved_price` only.

    `recurring_rate`/`upfront_fee` are independently `None` when their respective row is
    absent: `upfront_fee=None` is the expected, normal shape for `no_upfront` (there's no
    upfront row to have); `recurring_rate=None`, or `upfront_fee=None` for a
    `partial_upfront`/`all_upfront` combination, is a real pricing-data gap the caller must
    treat as unpriceable (FR-005), never substituted or guessed.
    """

    recurring_rate: float | None
    upfront_fee: float | None


def lookup_reserved_price(
    *,
    sku: str,
    pricing_term: str,
    purchase_option: str,
    region: str,
    snapshot_date: str | None = None,
) -> ReservedPrice | None:
    """Return the recurring hourly rate and, when applicable, the one-time upfront fee for one
    Reserved-term sku/purchase_option — distinguished from each other by `unit` ("Hrs" vs.
    "Quantity"), not by row order, closing the bug where `lookup_price`'s ambiguous `LIMIT 1`
    (no `unit` filter) always silently returned the recurring row and dropped the upfront fee
    entirely (006, FR-002, FR-004).

    Returns `None` only when no row matches at all (any unit) — the same "nothing priceable"
    signal `lookup_price`/`resolve_units` already use. Requires a Reserved `pricing_term`
    (raises `ValueError` for `on_demand`, which has no lease/term to look up against — a
    programming error, not a data gap, so this fails loudly rather than returning nonsense).

    A same-unit combination that happens to have more than one matching row (a known,
    pre-existing characteristic of a few real SKUs' Reserved pricing data, unrelated to this
    fix — see quickstart.md's Notes) resolves to whichever row is read first, the same
    determinism `lookup_price` already relies on elsewhere.
    """
    snapshot_date = snapshot_date or resolve_latest_snapshot_date()
    term, lease_length = _TERM_MAP[pricing_term]
    if lease_length is None:
        raise ValueError(
            f"lookup_reserved_price requires a Reserved pricing_term, got {pricing_term!r}"
        )
    purchase = _PURCHASE_OPTION_MAP[purchase_option]

    query = (
        "SELECT unit, price FROM read_parquet(?) WHERE sku = ? AND term = ? "
        "AND REPLACE(lease_contract_length, ' ', '') = ?"
    )
    params: list[object] = [_price_fact_path(snapshot_date, region), sku, term, lease_length]
    if purchase is not None:
        query += " AND REPLACE(purchase_option, ' ', '') = ?"
        params.append(purchase)

    try:
        con = duckdb.connect(":memory:", read_only=False)
        rows = con.execute(query, params).fetchall()
    except duckdb.Error as exc:
        raise PricingDataUnavailableError(str(exc)) from exc

    if not rows:
        return None

    recurring_rate: float | None = None
    upfront_fee: float | None = None
    for unit, price in rows:
        if unit == "Hrs" and recurring_rate is None:
            recurring_rate = float(price)
        elif unit == "Quantity" and upfront_fee is None:
            upfront_fee = float(price)

    return ReservedPrice(recurring_rate=recurring_rate, upfront_fee=upfront_fee)


def resolve_units(
    selections: Sequence[tuple[str, str, str]],
    *,
    region: str,
    snapshot_date: str | None = None,
) -> dict[tuple[str, str, str], str | None]:
    """Batched billing-unit lookup for many (sku, pricing_term, purchase_option) tuples, all in
    `region` (spec FR-004, FR-005; 010-multi-region-support).

    One DuckDB query covers every distinct SKU involved; matching against each tuple's
    normalized term/purchase_option happens in Python — the same "resolve once per request,
    not once per row" discipline `lookup_price`'s caller already relies on for price
    (research.md #3), applied here so a whole Architecture's units cost one query, not N. Every
    `selections` tuple passed in one call must belong to the same region — a caller spanning
    multiple regions calls this once per region and merges the results (safe: AWS SKU codes are
    themselves region-scoped, so a SKU from one region never collides with another's).
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
        rows = con.execute(query, [_price_fact_path(snapshot_date, region), *skus]).fetchall()
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
