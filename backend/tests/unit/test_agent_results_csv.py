"""The result CSV (024, FR-020, SC-008, research R8): a basis block, then exactly the rows and
totals shown, rounded like the pane; unavailable cells empty with a reason, never 0; text cells
safe from spreadsheet formulas; a short ASCII filename."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime

from src.agent.results import csv_filename, write_csv
from src.models.schemas import AgentResultOut


def result(**overrides) -> AgentResultOut:
    data = {
        "id": uuid.uuid4(), "message_id": uuid.uuid4(), "seq": 1,
        "kind": "architecture_comparison", "title": "Three-tier web app: AWS vs Azure",
        "summary": "2 rows", "created_at": datetime(2026, 11, 13, tzinfo=UTC),
        "basis": {"question_kind": "architecture", "architecture": "Three-tier web app",
                  "duration": "1_month", "reference_side": "aws:us-east-1",
                  "usage": "as in the architecture", "assumptions": ["Hot access tier"]},
        "sides": [
            {"id": "aws:us-east-1", "provider": "aws", "region": "us-east-1", "term": "on_demand"},
            {"id": "azure:eastus", "provider": "azure", "region": "eastus",
             "region_guessed": True, "term": "on_demand"},
        ],
        "rows": [
            {"label": "Database", "where": "App tier", "cells": {
                "aws:us-east-1": {"product": "RDS db.r6g.xlarge", "amount": "380.1234"},
                "azure:eastus": {"product": "PostgreSQL E4ds_v5", "quality": "close",
                                 "amount": "468.005", "diff": "87.8816", "diff_pct": "23.12"},
            }},
            {"label": "Queue", "where": "App tier", "cells": {
                "aws:us-east-1": {"product": "SQS", "amount": "12"},
                "azure:eastus": {"status": "unmatched",
                                 "reason": "no product in the same category"},
            }},
        ],
        "totals": {"aws:us-east-1": {"amount": "380.1234", "partial": True},
                   "azure:eastus": {"amount": "468.005", "partial": True, "diff": "87.8816",
                                    "diff_pct": "23.12"}},
        "snapshots": {"aws": {"date": "2026-11-02", "revision": 2},
                      "azure": {"date": "2026-11-03", "revision": 1}},
        "not_compared": ["Queue (AZURE: no product in the same category)"],
    }
    data.update(overrides)
    return AgentResultOut.model_validate(data)


def rows_of(text: str) -> list[list[str]]:
    assert text.startswith("﻿")
    return list(csv.reader(io.StringIO(text[1:])))


def test_basis_block_then_table_then_totals():
    rows = rows_of(write_csv(result()))
    blank = rows.index([])
    basis = {r[0]: r[1] for r in rows[:blank]}
    assert basis["Comparison"] == "Three-tier web app: AWS vs Azure"
    assert basis["Duration"] == "1 month (31 days)"
    assert basis["Currency"] == "USD"
    assert basis["AWS"] == "region us-east-1; term on demand; snapshot 2026-11-02 r2; reference"
    assert basis["Azure"] == "region eastus (guessed); term on demand; snapshot 2026-11-03 r1"
    assert basis["Assumptions"] == "Hot access tier"
    header, database, queue, total, not_compared = rows[blank + 1:]
    assert header == ["Service", "Where", "AWS product", "AWS amount", "Azure product",
                      "Azure match", "Azure amount", "Azure diff", "Azure diff %", "Status"]
    assert database == ["Database", "App tier", "RDS db.r6g.xlarge", "380.12",
                        "PostgreSQL E4ds_v5", "close", "468.01", "87.88", "23.1", ""]
    assert queue == ["Queue", "App tier", "SQS", "12.00", "", "", "", "", "",
                     "Azure no equivalent: no product in the same category"]
    assert total == ["Total (partial)", "", "", "380.12", "", "", "468.01", "87.88", "23.1", ""]
    assert not_compared == ["Not compared", "Queue (AZURE: no product in the same category)"]


def test_unavailable_cells_are_never_zero():
    text = write_csv(result())
    queue = next(r for r in rows_of(text) if r and r[0] == "Queue")
    assert "0" not in queue[4:9] and "0.00" not in queue[4:9]


def test_text_cells_cant_become_formulas_but_negative_numbers_stay_numbers():
    evil = result(title='=HYPERLINK("http://x","y")')
    evil.rows[0].where = "+cmd"
    evil.rows[0].cells["azure:eastus"].diff = -5
    evil.rows[0].cells["azure:eastus"].diff_pct = -1.25
    rows = rows_of(write_csv(evil))
    assert rows[0][1] == "'=HYPERLINK(\"http://x\",\"y\")"
    database = next(r for r in rows if r and r[0] == "Database")
    assert database[1] == "'+cmd"
    assert database[7:9] == ["-5.00", "-1.3"]


def test_names_with_commas_quotes_and_newlines_stay_one_cell():
    tricky = result()
    tricky.rows[0].label = 'DB, "primary"\nnode'
    rows = rows_of(write_csv(tricky))
    database = next(r for r in rows if r and r[0].startswith("DB"))
    assert database[0] == 'DB, "primary"\nnode'
    assert len(database) == 10


def test_two_regions_of_one_provider_get_their_own_columns():
    two = result(
        sides=[{"id": "aws:us-east-1", "provider": "aws", "region": "us-east-1",
                "term": "on_demand"},
               {"id": "aws:eu-west-1", "provider": "aws", "region": "eu-west-1",
                "term": "on_demand"}],
        rows=[{"label": "Storage", "cells": {
            "aws:us-east-1": {"amount": "1"}, "aws:eu-west-1": {"amount": "2", "diff": "1",
                                                                "diff_pct": "100"}}}],
        totals={"aws:us-east-1": {"amount": "1"}, "aws:eu-west-1": {"amount": "2"}},
        basis={"question_kind": "category", "category": "storage", "duration": "1_month",
               "reference_side": "aws:us-east-1", "usage": "1 TB stored"},
        not_compared=[],
    )
    rows = rows_of(write_csv(two))
    header = rows[rows.index([]) + 1]
    assert header == ["Service", "AWS us-east-1 product", "AWS us-east-1 amount",
                      "AWS eu-west-1 product", "AWS eu-west-1 match", "AWS eu-west-1 amount",
                      "AWS eu-west-1 diff", "AWS eu-west-1 diff %", "Status"]
    assert rows[-1][0] == "Total"


def test_filename_is_short_ascii():
    assert csv_filename(result()) == "comparison-three-tier-web-app-aws-vs-azure-2026-11-13.csv"
    long = csv_filename(result(title="Ünïcødé " + "x" * 200))
    assert long.isascii() and len(long) <= 80 and long.endswith("-2026-11-13.csv")


def test_a_tiny_negative_rounds_to_an_unsigned_zero_like_the_pane():
    tiny = result()
    tiny.rows[0].cells["azure:eastus"].diff = "-0.004"
    tiny.rows[0].cells["azure:eastus"].diff_pct = "-0.04"
    database = next(r for r in rows_of(write_csv(tiny)) if r and r[0] == "Database")
    assert database[7:9] == ["0.00", "0.0"]
