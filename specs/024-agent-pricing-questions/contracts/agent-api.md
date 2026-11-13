# Contract: Agent API Changes in 024

These are additions to 023's `contracts/agent-api.md`. All routes are under `/api/v1`, use the
Bearer header, and are defined with Pydantic models (Principle IV).

## Stream: new `result` event

On `POST /agent/session/messages` and `…/retry`:

| `event` | `data` |
|---|---|
| `result` | `AgentResultOut` (below), sent as soon as the operation that created it finishes, before the rest of the answer text |

Ordering is unchanged otherwise. A stream still ends with `done` or `error`. A result created
before an `error` is kept and stays linked to the agent message, which is saved with what was
written.

## Stream: `status` event gains progress

`AgentStatusEvent` gains optional fields, which stay absent for the existing states:

```json
{"state": "running_operation", "label": "Matching services", "done": 12, "total": 20}
```

The panel shows "Matching services (12 of 20)…". Without the fields it shows the existing
text.

## Operation time limit

An operation that runs longer than the agent timeout setting is stopped:
- its `operation` event has `outcome: "timeout"`;
- the activity log row records the same;
- the answer continues, and the model explains that it couldn't finish.

This isn't an `error` event, and the message isn't marked failed.

## `GET /agent/session` (extended)

`AgentSessionDetailOut` gains:
- `results: AgentResultOut[]`, in `seq` order;
- `result_ids: uuid[]` on each `AgentMessageOut` (empty for user messages and plain answers).

## `GET /agent/session/results/{result_id}/csv`

- `200 text/csv; charset=utf-8`, with a UTF-8 BOM, and
  `Content-Disposition: attachment; filename="<name>.csv"`.
- The filename is `comparison-<title-slug>-<YYYY-MM-DD>.csv`, ASCII, at most 80 characters.
- `404` when the result isn't in the caller's open session (another user's, or expired).
- Guests get `403` as with the other agent routes.

Layout:

```text
Comparison,Three-tier web app: AWS vs Azure
Duration,1 month (31 days)
Currency,USD
AWS,region us-east-1; term on demand; snapshot 2026-11-02 r2
Azure,region eastus (guessed); term on demand; snapshot 2026-11-03 r1
Assumptions,Hot access tier; Locally redundant storage

Service,Where,AWS product,AWS amount,Azure product,Azure match,Azure amount,Azure diff,Azure diff %,Status
Database,App tier,RDS db.r6g.xlarge PostgreSQL,380.12,PostgreSQL Flexible Server E4ds_v5,close,468.00,87.88,23.1,
Queue,App tier,SQS standard,12.00,,no equivalent,,,,"unmatched: no product in the same category"
Total (partial),,,1203.10,,,1349.55,146.45,12.2,
```

- Amounts are rounded to 2 decimal places with the same function as the pane.
- Unavailable, unmatched and unconvertible cells are empty, with a reason in `Status`; they
  are never 0.
- Each further side adds its own product, match, amount, diff and diff % columns. Column
  headers name the provider, plus the region when one provider appears in more than one side
  (for example `AWS us-east-1 amount`, `AWS eu-west-1 amount`).
- **Formula safety**: a text cell starting with `=`, `+`, `-`, `@`, a tab or a carriage return
  is written with a leading `'`, so spreadsheet tools show it as text. Number cells (amounts,
  diffs, %) are written unchanged, so negative differences stay numbers.

## Schemas (Pydantic → generated TS)

```text
AgentResultOut {
  id: uuid, message_id: uuid, seq: int,
  kind: "category_comparison" | "architecture_comparison",
  title: str, summary: str,
  basis: AgentResultBasis, sides: AgentResultSide[],
  rows: AgentResultRow[], totals: dict[str, AgentResultTotal],   // keyed by side id
  snapshots: dict[ProviderCode, {date: str, revision: int}],
  created_at: datetime
}
AgentResultSide { id: str, provider: ProviderCode, region: str, region_guessed: bool, term: str }
AgentResultRow { label: str, where: str | null, cells: dict[str, AgentResultCell] }   // side id
AgentResultCell {
  product: str | null, quality: MatchQuality | null, shown_quality: MatchQuality | null,
  quality_reason: str | null, differences: str[],
  amount: Decimal | null, diff: Decimal | null, diff_pct: Decimal | null,
  status: "ok" | "unavailable" | "unmatched" | "unconvertible", reason: str | null
}
AgentResultTotal { amount: Decimal | null, partial: bool, diff: Decimal | null, diff_pct: Decimal | null }
MatchQuality = "exact" | "close" | "partial" | "no_equivalent"
AgentResultEvent { event: "result", result: AgentResultOut }
```

Decimals are serialised as strings, as elsewhere in the API.

## Preferences

`PUT /preferences` (existing) accepts `workspace.agent_results: {split: 0.3–0.75}`. Out of
range values get `422`.
