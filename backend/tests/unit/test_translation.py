"""The mapping table's cost difference and caveats (026, research R6, FR-015), from fabricated
rows: the difference is over rows priced on both sides only, and a left-out or unpriceable row is
never a saving."""

from __future__ import annotations

import uuid
from decimal import Decimal

from src.agent import translation
from src.agent.proposals import Priced


def _row(label, where, source, match=None, status="matched", quality="exact",
         origin="seeded", reason=None):
    return {"where": where,
            "source": {"label": label, "region": "us-east-1", "quantity": "1", "unit": "Hrs",
                       "amount": source},
            "status": status,
            "match": None if match is None else {"label": f"{label} match", "region": "eastus",
                                                 "quantity": "1", "unit": "1 Hour",
                                                 "size": None, "amount": match},
            "quality": quality if match is not None else None,
            "origin": origin if match is not None else None,
            "differences": [], "reason": reason, "assumptions": [], "alternatives": 0}


def _priced(provider, total, unpriceable=()):
    return Priced(Decimal(total), bool(unpriceable), {},
                  {uuid.uuid4(): r for r in unpriceable},
                  {"provider": provider, "date": "2026-11-02", "revision": 1})


ROWS = [
    _row("VM", "Web", "100", "80", quality="close"),
    _row("DB", "Data", "200", "260"),
    _row("Disk", "Data", "10", "11"),
    _row("Queue", "Web", "5", "4", quality="partial", origin="chosen_by_user"),
    _row("CDN", "Web", "50", status="no_equivalent", reason="no equivalent"),
    _row("LB", "Web", None, "7", status="unpriceable", reason="can't be priced in the original"),
]


def test_the_difference_is_over_rows_priced_on_both_sides():
    summary = translation.cost_difference(ROWS, _priced("aws", "365"), _priced("azure", "362"),
                                          "1_month")
    compared = summary["compared"]
    assert compared["rows"] == 4
    assert Decimal(compared["original"]) == 315
    assert Decimal(compared["translation"]) == 355
    assert Decimal(compared["diff"]) == 40
    assert Decimal(compared["diff_pct"]).quantize(Decimal("0.01")) == Decimal("12.70")
    # The CDN's $50 (left out) and the unpriceable LB are not a saving or a cost.
    assert len(summary["left_out"]) == 2
    assert summary["translation_total"]["partial"] is True
    assert summary["original_total"]["partial"] is False
    assert summary["snapshots"] == {"aws": "2026-11-02", "azure": "2026-11-02"}


def test_drivers_are_the_three_largest_differences():
    summary = translation.cost_difference(ROWS, _priced("aws", "365"), _priced("azure", "362"),
                                          "1_month")
    assert [(d["label"], Decimal(d["diff"])) for d in summary["drivers"]] == [
        ("DB", Decimal(60)), ("VM", Decimal(-20)), ("Disk", Decimal(1))]


def test_not_exact_names_close_and_chosen_partial_matches():
    summary = translation.cost_difference(ROWS, _priced("aws", "365"), _priced("azure", "362"),
                                          "1_month")
    assert summary["not_exact"] == ["VM → VM match: close",
                                    "Queue → Queue match: partial, chosen by you"]


def _record(rows, regions=(), why=None):
    summary = translation.cost_difference(rows, _priced("aws", "1"), _priced("gcp", "1"),
                                          "1_month")
    return {"summary": summary,
            "regions": [{"source": s, "target": t, "guessed": g} for s, t, g in regions],
            "term": {"used": "on demand", "why": why}}


def test_caveats_name_everything_a_cost_answer_must_say():
    record = _record(ROWS, regions=[("us-east-1", "eastus", True)],
                     why="the original uses reserved 1-year")
    caveats = translation.caveats(record)
    text = " | ".join(caveats)
    assert "CDN in Web: no equivalent" in text
    assert "LB in Web" in text
    assert "Queue → Queue match: partial, chosen by you" in text
    assert "VM → VM match: close" in text
    assert "regions guessed: us-east-1 → eastus" in text
    assert "pricing term on demand: the original uses reserved 1-year" in text
    assert "the totals are partial" in text


def test_a_complete_exact_translation_has_no_caveats():
    rows = [_row("VM", "Web", "100", "80"), _row("DB", "Data", "200", "260")]
    assert translation.caveats(_record(rows)) == []
