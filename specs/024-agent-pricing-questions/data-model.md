# Data Model: Agent Pricing Questions and Comparisons

**Feature**: 024-agent-pricing-questions | **Date**: 2026-11-13

## 1. Persisted (Postgres, migration `0011_agent_results`)

### `agent_results` (new)

One comparison result shown in the Results pane (spec US6, FR-013, FR-018–FR-021).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `session_id` | UUID FK → `agent_sessions.id` ON DELETE CASCADE, indexed | Results go when the session goes (023's 3-day expiry, or a new session) |
| `message_id` | UUID FK → `agent_messages.id` ON DELETE CASCADE | The **user** message whose answer produced it. The agent message is only written when the answer ends, and a failed answer has none, so results hang off the question; the API reports each result on the agent message that answered that question (`result_ids`), or on the user message when the answer failed |
| `seq` | int | Order within the session (1, 2, …); unique with `session_id` |
| `kind` | varchar(30) | `category_comparison` or `architecture_comparison`; check constraint |
| `title` | varchar(200) | e.g. "Three-tier web app: AWS vs Azure, GCP" |
| `summary` | varchar(200) | the card's line, e.g. "14 rows · Azure total +12.4% (partial)" |
| `basis` | JSONB | see §3 Basis |
| `sides` | JSONB | ordered list of Side (§3), reference first, e.g. `aws:us-east-1`, `azure:eastus`, `gcp:us-east1` |
| `rows` | JSONB | list of Row (§3); cells keyed by side id |
| `totals` | JSONB | per side id: `{amount: "…" \| null, partial: bool}` plus differences |
| `snapshots` | JSONB | per provider: `{date, revision}` (one snapshot per provider, shared by its sides) |
| `created_at` | timestamptz | server default now() |

Constraints: `UNIQUE (session_id, seq)`; `CHECK kind IN (...)`.

Access rule: rows are read only through the owner's session (the same check as
`GET /agent/session`); there's no cross-user route (FR-021).

Principle II note: these are records of what the agent showed (like `agent_messages.content`),
with the snapshot revision per provider. They're never read as a source of prices. Every new
comparison prices afresh through the engine.

### `user_preferences.workspace` (JSON, existing)

`WorkspacePreferences` gains:

| Field | Type | Validation |
|---|---|---|
| `agent_results` | `AgentResultsPreferences \| None` | `{split: float}`, 0.3 ≤ split ≤ 0.75 (the conversation's share of the width) |

No change to `agent_sessions`, `agent_messages` or `agent_operations`. The activity log
records the new operations as it already does (FR-015).

## 2. Per message, in memory (not persisted)

### MatchBook

Lives beside the `FigureBook` for one agent message (research R7).

- `sources`: `S1…` → SourceProduct `{provider, region, service_code, sku, label, where,
  usage_quantity, unit, pricing_term, profile}`.
- `candidates`: `C1…` → Candidate `{source_ref | null, provider, region, service_code, sku,
  label, profile, quality, differences, usage: {quantity, unit, converted_from, factor} |
  {unconvertible: reason}, options (gcp_machine / azure_vm), price_types}`.

The references are valid only within the message. A pick of an unknown reference is a tool
error.

### ProductProfile (research R2)

`function`, `category`, `specs {vcpu, memory_gib, os, engine, storage_class, redundancy, ha,
media}` (each optional), `unit_kind`.

### Figure (extended)

Gains `kind`: `money` (default, rendered `$1,234.56`) or `percent` (rendered `+12.3%` /
`−4.0%`).

## 3. Result JSON shapes

### Side

A column group of the result: one provider in one region. Keying by side, not by provider,
lets one result compare several regions of the same provider (spec edge case).

```json
{"id": "aws:us-east-1", "provider": "aws", "region": "us-east-1",
 "region_guessed": false, "term": "on_demand"}
```

The id is `<provider>:<region>`, unique within a result.

### Basis

```json
{
  "question_kind": "architecture",          // category | architecture
  "architecture": "Three-tier web app",     // architecture only
  "category": "storage",                    // category, or architecture part ("my storage")
  "duration": "1_month",
  "currency": "USD",
  "reference_side": "aws:us-east-1",        // the sides themselves are in `sides`
  "usage": "as in the architecture",        // or e.g. "1 TB stored for 1 month"
  "assumptions": ["Hot access tier", "Locally redundant storage"]
}
```

### Row

```json
{
  "label": "Database",                       // the source service, or the category product
  "where": "App tier",                       // architecture only
  "cells": {
    "aws:us-east-1": {"product": "RDS db.r6g.xlarge PostgreSQL", "quality": null,
              "amount": "380.1234", "status": "ok"},
    "azure:eastus":  {"product": "PostgreSQL Flexible Server E4ds_v5", "quality": "close",
              "shown_quality": "close", "quality_reason": null,
              "differences": ["memory 32 GiB vs 32 GiB", "x86 vs ARM"],
              "amount": "468.0000", "status": "ok",
              "diff": "87.8766", "diff_pct": "23.1"}
  }
}
```

- A cell's `status` is one of `ok`, `unavailable`, `unmatched` or `unconvertible`, and
  `reason` is set when it isn't `ok`.
- `amount`, `diff` and `diff_pct` are null unless the status is `ok` on both the cell and the
  reference.
- The reference side's cells carry no quality or diff.

## 4. State

- A result is created once, when `price_matches` or `price_products` finishes with two or more
  providers and at least one priced row. It's immutable afterwards.
- If nothing could be priced, no result is made (spec edge case).
- Results are deleted with their session.
- In the frontend, the Results pane is in one of these states:
  - hidden: there are no results, or the user closed it;
  - open, showing result *k* of *n*;
  - stacked, the same states laid out below the conversation when the tab is narrow.
