# Contract: Agent API Changes

**Feature**: 026 | All in OpenAPI through Pydantic (Principle IV); regenerate
`frontend/src/api/generated/schema.d.ts`.

No new routes. 025's proposal routes handle translations:

| Route | Change |
|---|---|
| `GET /agent/session` | proposals of kind `translate` carry `translation` (below); `stale` is computed for them too (R9) |
| `POST /agent/proposals/{id}/accept` | for `translate`: refuse a stale one with 409 `{"error": "stale_translation", "message": "The original or the pricing data changed since this translation. Ask me to translate it again."}` and set it `expired`; otherwise create the architecture as for `create` and return `opened` |
| `POST /agent/proposals/{id}/reject`, `/undo`, `/redo` | unchanged; `translate` behaves as `create` |
| stream event `proposal` | unchanged shape; carries the translation proposal |

## Schemas

```text
ProposalKind = "change" | "create" | "import" | "translate"

AgentProposalOut += translation: TranslationOut | null

TranslationOut {
  source_architecture_id: uuid, source_name: str, source_provider: str, target_provider: str,
  regions: [{source: str, target: str, guessed: bool}],
  term: {used: str, why: str | null},
  mapping_version: {seed: int, snapshots: {str: date}},
  rows: [MappingRowOut], summary: CostDifferenceOut
}

MappingRowOut {
  where: str,
  source: {label: str, region: str, quantity: str, unit: str | null, amount: str | null},
  status: "matched" | "no_equivalent" | "partial_only" | "not_sold_in_region" | "unpriceable",
  match: {label: str, region: str, quantity: str, unit: str | null, size: str | null,
          amount: str | null} | null,
  quality: "exact" | "close" | "partial" | null,
  origin: "seeded" | "automatic" | "chosen_by_user" | null,
  differences: [str], reason: str | null, assumptions: [str], alternatives: int
}

CostDifferenceOut {
  duration: str,
  original_total: {amount: str | null, partial: bool},
  translation_total: {amount: str | null, partial: bool},
  compared: {original: str | null, translation: str | null, diff: str | null,
             diff_pct: str | null, rows: int},
  left_out: [str], drivers: [{where: str, label: str, diff: str}], not_exact: [str],
  snapshots: {str: date}
}
```

Amounts are unrounded decimal strings; the frontend rounds with 023's helpers.

## Activity log (023)

New operation entries `find_translation`, `propose_translation` and `describe_translation`. The proposal entries
(`accept_proposal`, `reject_proposal`, `undo_proposal`, `redo_proposal`) for a translation add
`mapping_version` and both `snapshots` to their summary (FR-017).
