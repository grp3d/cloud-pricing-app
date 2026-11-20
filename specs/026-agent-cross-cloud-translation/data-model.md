# Data Model: Agent Cross-Cloud Architecture Translation

**Feature**: 026-agent-cross-cloud-translation | **Date**: 2026-11-19

One new table (`service_mappings`) and one column and kind on 025's `agent_proposals`, both in
migration `0013_service_mappings`. Architectures, collections, services and connectors are
unchanged; a translation is saved through 025's applier like any created architecture.

## 1. `service_mappings` (new, Postgres; Principle II linking data)

Seed mappings generated from 022's rules (research R3, R4). Read-only to the app at run time;
replaced only by a migration with a new version.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `version` | int, not null | the seed file's version; every row of one release has the same |
| `source_provider` | varchar(10), not null | `aws` in this release |
| `source_key` | varchar(400), not null | the source product key (research R2) |
| `target_provider` | varchar(10), not null | `gcp` or `azure` |
| `alternative` | smallint, not null | 1, 2…: distinct targets for the same source (FR-008) |
| `part` | smallint, not null | 1, 2…: lines of one target (Glue → vCPU and RAM) |
| `target_key` | varchar(400), null | null means "no equivalent" |
| `target_service_code` | varchar(100), null | the target's service, to search within it |
| `target_sku` | varchar(200), null | 022's own SKU, tried first in the target region (a stable identifier); otherwise the key decides |
| `target_options` | jsonb, null | e.g. a GCP machine shape `{kind: gcp_machine, vcpus, memory_gib}` |
| `quantity_factor` | numeric(20,10), null | target quantity = source quantity × factor (R4) |
| `note` | text, null | 022's note ("Aurora's single writer instance: a zonal Cloud SQL instance") |
| `omit_reason` | text, null | 022's reason when `target_key` is null |
| `origin` | varchar(20), not null | `seed_022` |

No labels or prices are stored (Principle II): the table holds identifiers (product keys and a
service code), 022's factor, options and notes. Labels for the mapping table are built at run
time from the catalog rows (024's `product_label`).

Constraints: unique (`version`, `source_provider`, `source_key`, `target_provider`,
`alternative`, `part`); `target_key` and `omit_reason` are exactly one of null; check
`source_provider <> target_provider`.

## 2. `agent_proposals` (025, changed)

- `kind` check gains `translate`.
- New column `translation` jsonb, null (set only for `translate`), holding:

| Field | Meaning |
|---|---|
| `source_architecture_id` | also in the existing column of the same name |
| `source_name`, `source_provider`, `target_provider` | |
| `regions` | `[{source, target, guessed}]` (FR-010) |
| `term` | the pricing term used on the target, and why (GC-4) |
| `source_fingerprint` | 025's fingerprint of the source state at proposal time (R9) |
| `mapping_version` | `{seed: int, snapshots: {aws: date, gcp\|azure: date}}` (FR-001) |
| `snapshot_meta` | `{provider: {date, revision}}`, behind the figures and the answer footer |
| `rows` | Mapping Table Rows (§3), in canvas order |
| `summary` | Cost Difference Summary (§4) |
| `choices` | the user's picks: `[{source_key, where, picked, chosen_by_user}]` |

`base_state` stays null (nothing exists to undo to); `target_state` is the translated state; the
existing `cost` holds the translated architecture's 025 cost summary, so the card and accept work
unchanged.

**State transitions**: as 025 (`pending` → `accepted` | `rejected` | `superseded` | `expired`;
undo `available` → `undone` → `available`). A pending translation becomes **stale** when the
source's current fingerprint, the current seed version, or either provider's current pricing
snapshot date differs from the stored ones; accept
then refuses and sets `expired` (R9). A later `propose_translation` in the session sets the
pending one to `superseded` (US5).

## 3. Mapping Table Row (in `translation.rows`)

| Field | Meaning |
|---|---|
| `where` | the source collection or connector name |
| `source` | `{label, service_code, sku, region, quantity, unit, amount}` |
| `status` | `matched` \| `no_equivalent` \| `partial_only` \| `not_sold_in_region` \| `unpriceable` |
| `match` | null, or `{label, service_code, sku, region, quantity, unit, options, amount}` |
| `quality` | `exact` \| `close` \| `partial` \| null (024's rules) |
| `origin` | `seeded` \| `automatic` \| `chosen_by_user` \| null |
| `differences` | app-written facts ("arm64 vs x86_64") |
| `reason` | why there is no match, or why it can't be priced |
| `assumptions` | e.g. usage carried over by factor ×4; size chosen; term |
| `alternatives` | count of other valid equivalents (FR-008), for the view |

Validation: one row per source service (SC-001); `matched` rows have a `match` and an `origin`;
`chosen_by_user` only with `quality = partial` (FR-004); amounts are the engine's, as strings.

## 4. Cost Difference Summary (in `translation.summary`)

| Field | Meaning |
|---|---|
| `duration` | e.g. `1_month` |
| `original_total`, `translation_total` | each architecture priced whole; `partial` flags |
| `compared` | `{original, translation, diff, diff_pct, rows}`: over rows priced on both sides (R6) |
| `left_out` | labels of rows not compared, with reasons |
| `drivers` | up to three `{where, label, diff}`, largest absolute difference first |
| `not_exact` | labels of matched rows that aren't exact, naming `chosen_by_user` ones |
| `snapshots` | each provider's pricing snapshot date |

All amounts are unrounded engine values stored as strings; the view and the model's figure
references round them (023).

## 5. Not stored

- Automatic matches (computed per translation by 024's matcher, R3).
- Partial offers: recorded in the activity log's `find_translation` summary and read from there
  (R7).
