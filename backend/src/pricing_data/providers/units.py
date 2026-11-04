"""Azure and GCP billing units → the app's unit classes (019, research R7).

Each provider's source unit is turned into the existing `UnitClassification` (`duration.py`:
`no_period`, `fixed_period`, `unrecognized`) through an explicit table, in the style of the AWS
table: a form that isn't in the table is `unrecognized`, so the line is reported unpriceable and
never guessed (FR-007, Constitution Principle I).

A published price can be for a block of units (Azure `10K`, `100 Hours`; GCP `unit_quantity`).
The adapters divide the price by that block size, so a selection's quantity is always in the
base unit (hours, GB, operations) and cost is rate × quantity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from src.pricing_data.duration import UnitClassification

_NO_PERIOD = UnitClassification(category="no_period")
_MONTH = UnitClassification(category="fixed_period", period_days=31)
_DAY = UnitClassification(category="fixed_period", period_days=1)
UNRECOGNIZED = UnitClassification(category="unrecognized")


@dataclass(frozen=True)
class ParsedUnit:
    """A source unit as (block size, base unit) and its unit class."""

    multiplier: Decimal
    base: str
    classification: UnitClassification


# --- Azure `unit_of_measure` -------------------------------------------------------------------
# Forms are "<number>[K|M] <base>", e.g. `1 Hour`, `100 Hours`, `1 GB/Month`, `10K`, `1/Month`.
# The base after the number, normalized, → its class. An empty base is a plain count.
_AZURE_BASES: dict[str, UnitClassification] = {
    "": _NO_PERIOD,  # `10K`, `1M`, `1`: a count of operations, transactions, messages…
    "Hour": _NO_PERIOD,
    "Hours": _NO_PERIOD,
    "Minute": _NO_PERIOD,
    "Minutes": _NO_PERIOD,
    "Second": _NO_PERIOD,
    "Seconds": _NO_PERIOD,
    "GB": _NO_PERIOD,
    "TB": _NO_PERIOD,
    "GB/Hour": _NO_PERIOD,
    "/Hour": _NO_PERIOD,
    "GB/Month": _MONTH,
    "TB/Month": _MONTH,
    "/Month": _MONTH,
    "/Day": _DAY,
    "GB/Day": _DAY,
}
_AZURE_FORM = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KM])?\s*(.*?)\s*$")
_SCALE = {None: Decimal(1), "K": Decimal(1000), "M": Decimal(1_000_000)}


def parse_azure_unit(unit_of_measure: str | None) -> ParsedUnit:
    """`1 Hour` → (1, Hour, no period); `10K` → (10000, count, no period); `1 GB/Month` →
    (1, GB/Month, 31-day period). Anything else is `unrecognized`."""
    if not unit_of_measure:
        return ParsedUnit(Decimal(1), "", UNRECOGNIZED)
    match = _AZURE_FORM.match(unit_of_measure)
    if match is None:
        return ParsedUnit(Decimal(1), unit_of_measure, UNRECOGNIZED)
    number, scale, base = match.groups()
    try:
        multiplier = Decimal(number) * _SCALE[scale]
    except InvalidOperation:  # pragma: no cover - the regex only admits numbers
        return ParsedUnit(Decimal(1), unit_of_measure, UNRECOGNIZED)
    if multiplier <= 0:
        return ParsedUnit(Decimal(1), unit_of_measure, UNRECOGNIZED)
    base = base.replace(" /", "/")
    classification = _AZURE_BASES.get(base, UNRECOGNIZED)
    return ParsedUnit(multiplier, base, classification)


# --- GCP `unit` + `unit_quantity` --------------------------------------------------------------
# GCP units are UCUM-style codes (`h`, `GiBy.mo`, `GiBy`, `count`…); the price is for
# `unit_quantity` of them.
_GCP_UNITS: dict[str, UnitClassification] = {
    "h": _NO_PERIOD,
    "min": _NO_PERIOD,
    "s": _NO_PERIOD,
    "count": _NO_PERIOD,
    "By": _NO_PERIOD,
    "KiBy": _NO_PERIOD,
    "MiBy": _NO_PERIOD,
    "GiBy": _NO_PERIOD,
    "TiBy": _NO_PERIOD,
    "GBy": _NO_PERIOD,
    "GiBy.h": _NO_PERIOD,
    "GiBy.s": _NO_PERIOD,
    "mo": _MONTH,
    "GiBy.mo": _MONTH,
    "TiBy.mo": _MONTH,
    "MiBy.mo": _MONTH,
    "GBy.mo": _MONTH,
    "d": _DAY,
    "GiBy.d": _DAY,
}


def parse_gcp_unit(unit: str | None, unit_quantity: Decimal | int | str | None) -> ParsedUnit:
    """`h` with `unit_quantity` 1 → (1, h, no period). An unknown unit, or a missing or
    non-positive `unit_quantity`, is `unrecognized`."""
    try:
        quantity = Decimal(str(unit_quantity)) if unit_quantity is not None else None
    except InvalidOperation:
        quantity = None
    if not unit or quantity is None or quantity <= 0:
        return ParsedUnit(quantity or Decimal(1), unit or "", UNRECOGNIZED)
    return ParsedUnit(quantity.normalize(), unit, _GCP_UNITS.get(unit, UNRECOGNIZED))
