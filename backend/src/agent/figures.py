"""Figures (023-agent-foundation, research R1, FR-004, FR-005, FR-005a; constitution Principle I).

The model never writes an amount. Operations that return money add each amount to a
`FigureBook`, which gives it a reference (`F1`, `F2`, …) kept with its unrounded engine value.
The model writes `[[F1]]`; `FigureStreamFilter` replaces it with the value formatted as USD to
2 decimal places, and replaces any amount the model wrote itself with "[figure removed]".
Text is held back only as long as needed to tell whether it is a reference or an amount, so
answers still stream (FR-009). `footer` states the duration and the snapshot behind the
figures used, written by the app (FR-005a).

024 (research R7): a figure can also be a percentage (`kind="percent"`), rendered with a sign
and 1 decimal place ("+12.3%"), so differences in percent come from the app too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

DURATION_LABELS = {
    "1_day": "1 day",
    "1_month": "1 month (31 days)",
    "1_year": "1 year (365 days)",
}

REMOVED = "[figure removed]"
UNAVAILABLE = "[figure unavailable]"

# A reference, with any currency the model put around it ("$[[F1]]", "[[F1]] USD"): the rendered
# amount carries its own "$", so the extra one is dropped rather than doubled.
_REF = re.compile(r"(?:\$\s?|USD\s?)?\[\[(F\d+)\]\](?:\s?USD|%)?")
# Amounts the model may type itself: currency amounts, percentages, comma-grouped numbers and
# two-decimal numbers. Plain counts ("3 services", "31 days") don't match.
_NUM = r"\d[\d,]*(?:\.\d+)?"
_MONEY = re.compile(
    r"\$\s?" + _NUM + r"(?:\s?USD)?"
    r"|USD\s?\$?" + _NUM
    + r"|(?<![\w.])" + _NUM + r"\s?USD"
    r"|(?<![\w.])\d+(?:\.\d+)?\s?%"
    r"|(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?"
    r"|(?<![\w.])\d+\.\d{2}(?!\d)"
)
# 025: a number followed by a usage unit ("1,000 GB-Mo", "744.00 Hrs") is a quantity from the
# architecture, not money, so it stays. Units vary by provider, so the word after the number is
# matched by how it starts.
_UNIT_WORD = re.compile(r"\s?([A-Za-z][A-Za-z.\-]*)")
_UNIT_STEMS = (
    "kb", "mb", "gb", "gib", "tb", "tib", "pb", "terabyte", "gigabyte", "byte",
    "hr", "hour", "second", "minute", "lcu", "rpu", "dpu", "vcpu", "cpu", "core",
    "request", "putrequest", "readrequest", "writerequest", "quer", "object", "obj-",
    "mau", "shard", "update", "instance", "node", "iops", "lambda-gb",
    "execution", "invocation", "message", "operation", "event", "call",
)
_UNIT_EXACT = frozenset({"h", "s", "io", "ios"})


def _is_quantity(text: str, end: int) -> bool:
    match = _UNIT_WORD.match(text, end)
    if not match:
        return False
    word = match.group(1).lower()
    return word in _UNIT_EXACT or word.startswith(_UNIT_STEMS)


# A trailing run of characters that could still become part of a reference or an amount, or
# the unit after a number.
_HOLD = re.compile(r"[\[\]F\d$.,%USD \t]*(?:(?<=[\d ])[A-Za-z](?:[A-Za-z.\-]{0,18}[A-Za-z\-])?)?\Z")
# Characters a reference or an amount can start with.
_STARTS = frozenset("$[0123456789U")


def round_cents(amount: Decimal) -> Decimal:
    """USD to 2 decimal places, half-up: the one rounding the answer text, the Results pane and
    the CSV all use (024, SC-008)."""
    return Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def round_percent(amount: Decimal) -> Decimal:
    return Decimal(amount).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def format_usd(amount: Decimal) -> str:
    rounded = round_cents(amount)
    sign = "-" if rounded < 0 else ""
    return f"{sign}${abs(rounded):,.2f}"


def format_percent(amount: Decimal) -> str:
    rounded = round_percent(amount)
    sign = "+" if rounded > 0 else ""
    return f"{sign}{rounded:.1f}%"


@dataclass(frozen=True)
class Figure:
    ref: str
    amount: Decimal
    label: str
    duration: str | None
    # {provider: {"date": "YYYY-MM-DD", "revision": n}}
    snapshot: dict | None
    kind: Literal["money", "percent"] = "money"

    def render(self) -> str:
        return format_percent(self.amount) if self.kind == "percent" else format_usd(self.amount)


class FigureBook:
    """The amounts operations returned in one answer, by reference."""

    def __init__(self) -> None:
        self._figures: dict[str, Figure] = {}

    def add(self, amount: Decimal, label: str, *, duration: str | None = None,
            snapshot: dict | None = None, kind: Literal["money", "percent"] = "money") -> str:
        ref = f"F{len(self._figures) + 1}"
        self._figures[ref] = Figure(ref, Decimal(amount), label, duration, snapshot, kind)
        return ref

    def get(self, ref: str) -> Figure | None:
        return self._figures.get(ref)


class FigureStreamFilter:
    """Feed streamed text in; get text out with references rendered and model-typed amounts
    removed. Call `flush` at the end."""

    def __init__(self, book: FigureBook) -> None:
        self._book = book
        self._buffer = ""
        self.removed = 0
        self.used: list[str] = []

    def feed(self, chunk: str) -> str:
        self._buffer += chunk
        start = _HOLD.search(self._buffer).start()
        tail = self._buffer[start:]
        skip = 0
        while skip < len(tail) and tail[skip] not in _STARTS:
            skip += 1
        cut = start + skip
        ready, self._buffer = self._buffer[:cut], self._buffer[cut:]
        return self._process(ready)

    def flush(self) -> str:
        ready, self._buffer = self._buffer, ""
        return self._process(ready)

    def _process(self, text: str) -> str:
        if not text:
            return ""

        def remove(match: re.Match) -> str:
            if match.group(0)[0].isdigit() and not match.group(0).endswith(("%", "USD")) \
                    and _is_quantity(text, match.end()):
                return match.group(0)
            self.removed += 1
            return REMOVED

        def render(match: re.Match) -> str:
            figure = self._book.get(match.group(1))
            if figure is None:
                return UNAVAILABLE
            if figure.ref not in self.used:
                self.used.append(figure.ref)
            return figure.render()

        return _REF.sub(render, _MONEY.sub(remove, text))


def footer(book: FigureBook, used: list[str]) -> str | None:
    """'Prices for 1 month (31 days), snapshot 2026-11-02 r2' for the figures used, or None."""
    figures = [f for ref in used if (f := book.get(ref)) is not None and f.kind == "money"]
    if not figures:
        return None
    durations = []
    for figure in figures:
        if figure.duration and figure.duration not in durations:
            durations.append(figure.duration)
    snapshots: dict[str, str] = {}
    for figure in figures:
        for provider, snap in (figure.snapshot or {}).items():
            snapshots[provider] = f"{snap['date']} r{snap['revision']}"
    parts = []
    if durations:
        ordered = [d for d in DURATION_LABELS if d in durations]
        parts.append("Prices for " + " and ".join(DURATION_LABELS[d] for d in ordered))
    if len(snapshots) == 1:
        parts.append(f"snapshot {next(iter(snapshots.values()))}")
    elif snapshots:
        parts.append("snapshots " + ", ".join(f"{p} {s}" for p, s in sorted(snapshots.items())))
    return ", ".join(parts)
