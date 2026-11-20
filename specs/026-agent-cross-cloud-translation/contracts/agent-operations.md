# Contract: Translation Operations (model-facing)

**Feature**: 026 | Registered in `src/agent/operations_translate.py` with 023's operation
registry. The model sends references only (`M…`, `I…`, `S…`, `C…`), never ids or SKUs
(Principle VII). Errors are `ToolError` text the model can act on.

## `find_translation`

> Find the equivalent of every service of an architecture on another provider. Call this first
> for any request to translate, move or rebuild an architecture on another cloud.

**Input**

| Field | Type | Notes |
|---|---|---|
| `architecture` | string, optional | `M…` (own, from `list_my_architectures`) or `I…` (public); omitted = the open one |
| `provider` | `gcp` \| `azure` | the target |
| `regions` | `{source region: target region}`, optional | missing entries are guessed |
| `term` | string, optional | a target term the user chose; default on demand |

**Refusals (ToolError)**: no architecture named and none open ("Ask which architecture.");
source already on the target; a direction other than AWS → GCP or Azure, or several targets
("I can translate from AWS to GCP or Azure only, one at a time."); more than 100 items (with the
count); a target region unknown or without pricing data (with the nearest that has it, as a
guess).

**Output**

```text
{
  source: {name, provider, items},
  regions: [{source: "us-east-1", target: "eastus", guessed: true}],
  term: {used: "on demand", why: "the original uses reserved 1-year; terms don't carry over"},
  services: [
    {ref: "S1", where: "Web tier", label: "EC2 t4g.xlarge", usage: "730 h a day",
     status: "matched" | "choose" | "partial_only" | "no_equivalent" | "not_sold_in_region"
             | "unpriceable",
     default: "C1" | null,
     candidates: [{ref: "C1", label: "Azure D4s v5", quality: "close", origin: "seeded"
                   | "automatic", differences: ["x86_64 vs arm64"], usage: "730 h a day"}],
     reason: null | "022: no CloudFront prices"}
  ],
  needs_user: ["guessed regions R1", "S4 has 3 valid equivalents", "S7 has only partial matches"]
}
```

`choose` = several exact or close candidates (FR-008; `default` is the best quality, then the
lowest engine price). `partial_only` = offered to the user (recorded for R7); `default` is null.
The activity-log summary lists sources, statuses and the partial offers.

## `propose_translation`

> Propose the translation as a new architecture on the target provider. The user sees the
> mapping table and the cost difference beside you and decides; nothing is saved until they
> accept.

**Input**

| Field | Type | Notes |
|---|---|---|
| `architecture`, `provider`, `regions`, `term` | as `find_translation` | must match this message's `find_translation` |
| `picks` | `[{source: "S4", candidate: "C9"}]`, optional | a choice among candidates, or an offered partial candidate |
| `name` | string, optional | default: the original's name |

**Rules**

- Requires a `find_translation` result for the same architecture and provider in this message.
- A pick of a partial candidate is accepted only if that source was offered as `partial_only` in
  an **earlier message of this session** (R7); otherwise: "Ask the user whether to use this
  partial match first; it can be used only if they choose it."
- A pick that isn't one of the source's candidates is refused (US5 scenario 2).
- Supersedes this session's pending translation, if any.

**Output**

```text
{
  proposal: "Q3",
  status: "pending: shown to the user beside you; nothing is saved until they accept",
  rows: {matched: 14, left_out: 2, chosen_by_user: 1},
  cost: {original_total: "F1", translation_total: "F2", compared_diff: "F3",
         compared_pct: "F4", partial: true, drivers: [{label, diff: "F5"}]},
  caveats: ["CloudFront left out: no equivalent", "S7 Azure Cache: partial, chosen by the user",
            "regions guessed: eastus"]
}
```

Figures are figure references (023); the model writes `[[F3]]`, never numbers. The activity log
records the proposal, its rows' origins, the mapping version and both snapshots (FR-017).

## `describe_translation`

> Read the translation shown to the user: its totals, the difference and every caveat. Use it to
> answer a later question about a translation ("so which is cheaper?") instead of repeating
> figures from an earlier answer.

**Input**

| Field | Type | Notes |
|---|---|---|
| `proposal` | string, optional | a `Q…` reference; omitted = the session's pending translation, else the latest one |

**Refusals**: no translation in this session ("There's no translation in this conversation yet.").

**Output**: the same `cost` and `caveats` as `propose_translation`, plus `{proposal: "Q3",
status: "pending" | "accepted" | …, stale: bool, source, target_provider, rows: {matched,
left_out, chosen_by_user}}`. Read-only: it reads the stored record and makes no new match or
price; a stale translation says so, and the model offers to translate again.
