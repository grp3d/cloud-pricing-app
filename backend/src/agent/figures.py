"""Figures (023-agent-foundation, research R1, FR-004, FR-005, FR-005a; constitution Principle I).

The model never writes an amount. Operations that return money add each amount to a
`FigureBook`, which gives it a reference (`F1`, `F2`, …) kept with its unrounded engine value.
The model writes `[[F1]]`; `FigureStreamFilter` replaces it with the value formatted as USD to
2 decimal places, and replaces any amount the model wrote itself with "[figure removed]".
Text is held back only as long as needed to tell whether it is a reference or an amount, so
answers still stream (FR-009). `footer` states the duration and the snapshot behind the
figures used, written by the app (FR-005a).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

DURATION_LABELS = {
    "1_day": "1 day",
    "1_month": "1 month (31 days)",
    "1_year": "1 year (365 days)",
}

REMOVED = "[figure removed]"
UNAVAILABLE = "[figure unavailable]"

# A reference, with any currency the model put around it ("$[[F1]]", "[[F1]] USD"): the rendered
# amount carries its own "$", so the extra one is dropped rather than doubled.
_REF = re.compile(r"(?:\$\s?|USD\s?)?\[\[(F\d+)\]\](?:\s?USD)?")
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
# A trailing run of characters that could still become part of a reference or an amount.
_HOLD = re.compile(r"[\[\]F\d$.,%USD \t]*\Z")
# Characters a reference or an amount can start with.
_STARTS = frozenset("$[0123456789U")


def format_usd(amount: Decimal) -> str:
    rounded = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if rounded < 0 else ""
    return f"{sign}${abs(rounded):,.2f}"


@dataclass(frozen=True)
class Figure:
    ref: str
    amount: Decimal
    label: str
    duration: str | None
    # {provider: {"date": "YYYY-MM-DD", "revision": n}}
    snapshot: dict | None


class FigureBook:
    """The amounts operations returned in one answer, by reference."""

    def __init__(self) -> None:
        self._figures: dict[str, Figure] = {}

    def add(self, amount: Decimal, label: str, *, duration: str | None = None,
            snapshot: dict | None = None) -> str:
        ref = f"F{len(self._figures) + 1}"
        self._figures[ref] = Figure(ref, Decimal(amount), label, duration, snapshot)
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

        def remove(_match: re.Match) -> str:
            self.removed += 1
            return REMOVED

        def render(match: re.Match) -> str:
            figure = self._book.get(match.group(1))
            if figure is None:
                return UNAVAILABLE
            if figure.ref not in self.used:
                self.used.append(figure.ref)
            return format_usd(figure.amount)

        return _REF.sub(render, _MONEY.sub(remove, text))


def footer(book: FigureBook, used: list[str]) -> str | None:
    """'Prices for 1 month (31 days), snapshot 2026-11-02 r2' for the figures used, or None."""
    figures = [f for ref in used if (f := book.get(ref)) is not None]
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
