# Contract: Agent Operations Added in 024

These operations are registered in the 023 registry (`src/agent/operations.py`, or a sibling
module imported by it). They take the user and the open architecture from `OperationContext`,
never from the model. All of them are read-only (FR-014).

Each result is sent to the model as JSON data.
- Amounts are figure references (`F…`) and percentages are percent figure references.
- Products are match references (`S…` for sources, `C…` for candidates).
- The model never sees or sends a SKU for a pick.

## `find_matches`

For the open architecture, or part of it, it finds candidates on one or two target providers
in one call (FR-009a).

Input:

```json
{
  "target_providers": ["azure", "gcp"],          // 1–2, not the architecture's own provider
  "category": "storage",                         // optional: compute|storage|database|networking
  "target_regions": {"azure": "eastus"},         // optional per provider; else guessed (R6)
  "hints": {"S3": "premium ssd"}                 // optional: re-search one source (corrections)
}
```

Output:

```json
{
  "architecture": "Three-tier web app", "source_provider": "aws",
  "regions": {"azure": {"region": "eastus", "guessed": true}},
  "sources": [
    {"ref": "S1", "service": "Amazon RDS (Database Instance)", "where": "App tier",
     "usage": "730 Hrs", "term": "on_demand",
     "candidates": {"azure": [
       {"ref": "C4", "product": "…E4ds_v5", "quality": "close",
        "differences": ["…"], "usage": "730 hours", "terms": ["on_demand", "reservation_1y"]}
     ]}}
  ],
  "unmatched": [{"ref": "S7", "service": "AWS Glue", "provider": "azure",
                 "reason": "no product in the same category"}]
}
```

Errors (`ToolError`): no open architecture; a target equal to the source provider (the
message tells the model to say it's already on that provider); an unknown provider or region.

## `price_matches`

Prices the picks and creates the result (FR-013, FR-020).

Input:

```json
{
  "duration": "1_month",
  "terms": {"aws": "on_demand", "azure": "on_demand"},   // default on_demand, stated
  "picks": [
    {"source": "S1", "provider": "azure", "candidate": "C4"},
    {"source": "S2", "provider": "azure", "candidate": null},          // no equivalent
    {"source": "S3", "provider": "azure", "candidate": "C9",
     "shown_quality": "partial", "reason": "different performance tier"}
  ]
}
```

Rules:
- every source in the earlier `find_matches` must have one pick per target; a missing pick
  counts as `null`;
- `shown_quality` may only be lower than the app's label;
- a reference from another message is a tool error.

Output: `{result_id, title, totals: {aws: "F1", azure: "F2"}, differences: {azure: {amount:
"F3", pct: "F4"}}, partial: true, unavailable: [...], snapshots: {...}}`. The `result` stream
event is emitted (agent-api.md).

## `search_products`

Searches products for a category question (US1, US5).

Input:

```json
{
  "providers": ["azure", "gcp"],
  "category": "storage",
  "function": "object_storage",              // optional, from R2's list
  "regions": {"gcp": "us-central1"},         // optional; else guessed
  "text": "hot lrs",                         // optional search text per call
  "reference": "C2"                          // optional: compute quality against this pick
}
```

Output: per provider, up to 5 candidates `{ref, product, profile summary, quality (when a
reference is given), differences, unit, terms}` plus `regions` with `guessed` flags.

## `price_products`

Prices picked products for a usage (US1, US5).

Input:

```json
{
  "picks": ["C2", "C7"],                      // first is the reference
  "usage": {"quantity": "1", "unit": "TB"},   // converted per research R4
  "duration": "1_month",
  "terms": {"azure": "on_demand", "gcp": "on_demand"}
}
```

Output:
- 1 pick: `{figure: "F1", unit, snapshot}`, with no result.
- 2 or more picks: figures per provider, differences (amount and percent) against the
  reference, and `result_id`.
- A pick that can't be priced: `{status: "unavailable", reason}`, with no figure.

## `list_regions`

Input: `{provider, near?: "us-east-1"}`.

Output: the provider's regions that have pricing data, with names, and with `near` set the
guessed nearest (R6), labelled `guessed: true`.

## Time limit and progress (research R13)

- Every operation runs under the agent timeout setting (default 60 s). On overrun the model
  receives the tool error "The operation took too long and was stopped", and the log records
  `outcome: "timeout"`.
- `find_matches` calls `ctx.progress(done, total, "Matching services")` after each source
  product. The calls are throttled to one every 250 ms.

## Activity log

Every call is recorded as an `agent_operations` row as in 023:
- `inputs`: the arguments, with references;
- `summary`: counts, the regions, the picks with SKUs resolved, and `result_id`;
- `snapshot`: per provider.

The basis behind every figure can therefore be checked (FR-015).
