"""Comparison results (024, research R8, FR-013, FR-019–FR-021): saving a comparison as a result
the Results pane shows, and writing it as CSV.

A result is a record of what was shown (Principle II note in plan.md). The CSV and the pane use
the same rounding (`round_cents`, `round_percent`) and the same rows (SC-008). Text cells are
written so a spreadsheet can't run them as formulas: names come from users and imported
architectures (Principle VII).
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import UTC
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.compare import ComparisonOutcome, term_label
from src.agent.figures import DURATION_LABELS, round_cents, round_percent
from src.models.orm import AgentMessage, AgentResult, AgentSession
from src.models.schemas import AgentResultOut

PROVIDER_NAMES = {"aws": "AWS", "azure": "Azure", "gcp": "GCP"}
QUALITY_WORDS = {"exact": "exact", "close": "close", "partial": "partial",
                 "no_equivalent": "no equivalent"}
STATUS_WORDS = {"unavailable": "unavailable", "unmatched": "no equivalent",
                "unconvertible": "can't convert usage"}


def _dec(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _pct_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    rounded = round_percent(value)
    return f"{'+' if rounded > 0 else ''}{rounded:.1f}%"


def side_names(sides: list[dict]) -> dict[str, str]:
    """Column-group names: the provider, plus the region when a provider appears twice."""
    counts: dict[str, int] = {}
    for side in sides:
        counts[side["provider"]] = counts.get(side["provider"], 0) + 1
    return {side["id"]: (f"{PROVIDER_NAMES[side['provider']]} {side['region']}"
                         if counts[side["provider"]] > 1 else PROVIDER_NAMES[side["provider"]])
            for side in sides}


def _summary(outcome: ComparisonOutcome) -> str:
    rows = len(outcome.rows)
    parts = [f"{rows} row{'s' if rows != 1 else ''}"]
    names = side_names([s.out() for s in outcome.sides])
    target = next((s for s in outcome.sides[1:]
                   if outcome.totals[s.id]["diff_pct"] is not None), None)
    if target is not None:
        total = outcome.totals[target.id]
        text = f"{names[target.id]} total {_pct_text(total['diff_pct'])}"
        if total["partial"]:
            text += " (partial)"
        parts.append(text)
    elif all(t["amount"] is None for t in outcome.totals.values()):
        parts.append("totals not comparable")
    return " · ".join(parts)[:200]


async def create_result(session: AsyncSession, agent_session: AgentSession,
                        message: AgentMessage, outcome: ComparisonOutcome, *, kind: str,
                        title: str, basis: dict) -> AgentResult:
    """Save `outcome` as the session's next result, linked to the user `message`."""
    current = (await session.execute(
        select(func.max(AgentResult.seq)).where(AgentResult.session_id == agent_session.id)
    )).scalar_one()
    rows = []
    for row in outcome.rows:
        cells = {}
        for side_id, cell in row.cells.items():
            cells[side_id] = {
                "product": cell.product, "quality": cell.quality,
                "shown_quality": cell.shown_quality, "quality_reason": cell.quality_reason,
                "differences": list(cell.differences), "usage": cell.usage,
                "amount": _dec(cell.amount), "diff": _dec(cell.diff),
                "diff_pct": _dec(cell.diff_pct), "status": cell.status, "reason": cell.reason,
                "priced": None if cell.line is None else {
                    "service_code": cell.line.service_code, "sku": cell.line.sku,
                    "region": cell.line.region, "quantity": str(cell.line.quantity),
                    "pricing_term": cell.line.pricing_term,
                    "purchase_option": cell.line.purchase_option,
                    "options": cell.line.options},
            }
        rows.append({"label": row.label, "where": row.where, "cells": cells})
    totals = {side_id: {key: (_dec(value) if isinstance(value, Decimal) else value)
                        for key, value in total.items()}
              for side_id, total in outcome.totals.items()}
    result = AgentResult(
        session_id=agent_session.id, message_id=message.id, seq=(current or 0) + 1, kind=kind,
        title=title[:200], summary=_summary(outcome),
        basis={**basis, "not_compared": outcome.not_compared},
        sides=[side.out() for side in outcome.sides], rows=rows, totals=totals,
        snapshots=outcome.snapshots,
    )
    session.add(result)
    await session.flush()
    return result


def to_out(result: AgentResult) -> AgentResultOut:
    basis = dict(result.basis or {})
    not_compared = basis.pop("not_compared", [])
    return AgentResultOut.model_validate({
        "id": result.id, "message_id": result.message_id, "seq": result.seq,
        "kind": result.kind, "title": result.title, "summary": result.summary,
        "basis": basis, "sides": result.sides, "rows": result.rows, "totals": result.totals,
        "snapshots": result.snapshots, "not_compared": not_compared,
        "created_at": result.created_at,
    })


# --- CSV -----------------------------------------------------------------------------------------

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _safe_text(value: object) -> str:
    """A text cell a spreadsheet shows as text, never runs as a formula (CSV injection)."""
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_FORMULA_START) else text


def _unsigned_zero(value: Decimal) -> Decimal:
    return abs(value) if value == 0 else value  # "-0.00" → "0.00", as the pane shows it


def _money(value: Decimal | None) -> str:
    return "" if value is None else f"{_unsigned_zero(round_cents(value)):f}"


def _pct(value: Decimal | None) -> str:
    return "" if value is None else f"{_unsigned_zero(round_percent(value)):f}"


def write_csv(result: AgentResultOut) -> str:
    """The result as CSV: a basis block, a blank row, then the table and totals (FR-020)."""
    sides = [s.model_dump() for s in result.sides]
    names = side_names(sides)
    reference = result.basis.reference_side
    is_architecture = result.basis.question_kind == "architecture"
    buffer = io.StringIO()
    out = csv.writer(buffer, lineterminator="\r\n")

    def text_row(*cells: object) -> None:
        out.writerow([_safe_text(c) for c in cells])

    text_row("Comparison", result.title)
    if result.basis.architecture:
        text_row("Architecture", result.basis.architecture)
    if result.basis.category:
        text_row("Category", result.basis.category)
    text_row("Duration", DURATION_LABELS.get(result.basis.duration.value,
                                             result.basis.duration.value))
    text_row("Currency", result.basis.currency)
    for side in result.sides:
        snap = result.snapshots.get(side.provider)
        region = f"region {side.region}" + (" (guessed)" if side.region_guessed else "")
        snapshot = f"snapshot {snap.date} r{snap.revision}" if snap else "no snapshot"
        text_row(names[side.id], f"{region}; term {term_label(side.term, side.purchase_option)}; "
                 f"{snapshot}" + ("; reference" if side.id == reference else ""))
    text_row("Usage", result.basis.usage)
    if result.basis.assumptions:
        text_row("Assumptions", "; ".join(result.basis.assumptions))
    out.writerow([])

    header = ["Service"] + (["Where"] if is_architecture else [])
    for side in result.sides:
        name = names[side.id]
        header += [f"{name} product"]
        if side.id != reference:
            header += [f"{name} match"]
        header += [f"{name} amount"]
        if side.id != reference:
            header += [f"{name} diff", f"{name} diff %"]
    header.append("Status")
    text_row(*header)

    for row in result.rows:
        cells: list[object] = [_safe_text(row.label)]
        if is_architecture:
            cells.append(_safe_text(row.where or ""))
        status = []
        for side in result.sides:
            cell = row.cells.get(side.id)
            if cell is None:
                cells += [""] * (2 if side.id == reference else 5)
                continue
            cells.append(_safe_text(cell.product or ""))
            if side.id != reference:
                shown = cell.shown_quality or cell.quality
                cells.append(QUALITY_WORDS.get(shown, "") if shown else "")
            cells.append(_money(cell.amount) if cell.status == "ok" else "")
            if side.id != reference:
                cells += [_money(cell.diff), _pct(cell.diff_pct)]
            if cell.status != "ok":
                status.append(f"{names[side.id]} {STATUS_WORDS.get(cell.status, cell.status)}"
                              + (f": {cell.reason}" if cell.reason else ""))
        cells.append(_safe_text("; ".join(status)))
        out.writerow(cells)

    partial = any(t.partial for t in result.totals.values())
    totals: list[object] = ["Total (partial)" if partial else "Total"]
    if is_architecture:
        totals.append("")
    for side in result.sides:
        total = result.totals.get(side.id)
        totals.append("")
        if side.id != reference:
            totals.append("")
        totals.append(_money(total.amount) if total else "")
        if side.id != reference:
            totals += [_money(total.diff) if total else "", _pct(total.diff_pct) if total else ""]
    totals.append("")
    out.writerow(totals)
    for item in result.not_compared:
        text_row("Not compared", item)
    return "﻿" + buffer.getvalue()


def csv_filename(result: AgentResultOut) -> str:
    """`comparison-<title-slug>-<YYYY-MM-DD>.csv`, ASCII, at most 80 characters."""
    ascii_title = unicodedata.normalize("NFKD", result.title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-") or "result"
    date = result.created_at.astimezone(UTC).date().isoformat()
    room = 80 - len("comparison--") - len(date) - len(".csv")
    return f"comparison-{slug[:room].rstrip('-')}-{date}.csv"
