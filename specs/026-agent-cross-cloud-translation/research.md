# Research: Agent Cross-Cloud Architecture Translation

**Feature**: 026-agent-cross-cloud-translation | **Date**: 2026-11-19

The Technical Context had no open unknowns: the stack, storage, testing and limits are those of
023–025. These decisions settle how the spec's mapping data, matching, pricing and proposals are
built from what already exists.

## R1. Translation is a 025 "create" proposal with a translation record

**Decision**: a translation is a new proposal kind, `translate`, built with 025's `Draft` and
saved, accepted, rejected, undone and redone through 025's lifecycle exactly as `create` and
`import` are (accept creates a private architecture; undo soft-deletes it; redo restores it). The
proposal also stores a `translation` record: the mapping table, the cost difference summary, the
target regions, the user's choices, the mapping data version and the source's fingerprint.

**Rationale**: FR-009 asks for 025's behaviour unchanged. `propose_import` already copies a
source's collections, nesting, connectors and services into a `Draft`; translation is the same
walk with each service replaced by its match (FR-006). A separate kind lets the view, the card,
the activity log and the stale check treat it differently without touching `create` or `import`.

**Alternatives considered**: reusing `create` with an optional record (the stale check and the
view would branch on the record's presence instead of the kind, which is harder to read); a
separate translation table (duplicates 025's lifecycle).

## R2. A mapping is keyed by a region-independent product key, defined per provider

**Decision**: each adapter gets `product_key(item) -> str`, a key for a kind of product that is
the same in every region (clarification 2), and `find_by_key(region, key) -> CatalogItem | None`:

| Provider | Product key |
|---|---|
| AWS | `service_code` + `usagetype` with its region prefix removed (`USE1-BoxUsage:t4g.xlarge` → `BoxUsage:t4g.xlarge`) + `operation` |
| GCP | `service_id` + `display_name` with its location words removed by a reviewed pattern list ("in Americas", "running in EMEA", "for South Carolina (us-east1)") |
| Azure | `service_name` + `product_name` + `sku_name` + `meter_name` (the region is `armRegionName`, already separate) |

A GCP machine mapping also carries its shape (vCPU and memory) in the mapping's options, as
022's `gcp_machine` rules do.

**Rationale**: Principle III (provider quirks stay in the adapters). AWS SKUs are per region and
GCP SKUs sometimes span regions, so the SKU can't be the key; the attributes above are what makes
two regions' rows "the same product". The 022 seeds give a ready test: resolving each seed
mapping in 022's regions must return exactly 022's SKUs (R4).

**Alternatives considered**: per-region SKU pairs (rejected in clarification 2); the 019 Trends
`item_key` (it is the SKU, region-bound for AWS and Azure meters).

## R3. Mapping data: seed mappings in Postgres; automatic matches computed by 024's matcher

**Decision**:

- **Seed mappings** live in a new Postgres table, `service_mappings`, inserted once by migration
  `0013` from generated files `src/db/seed/service_mappings_{gcp,azure}.json`, as 0005, 0007 and
  0009 do for their seeds. Each row is one source product key → one target product key (or "no
  equivalent" with 022's reason), with a quantity factor and options. The file has a `version`;
  rows carry it.
- **Automatic matches** are not stored. For a source with no seed mapping, 024's
  `find_candidates` finds and rates candidates in the chosen target region, as `find_matches`
  does today. The "mapping data version" of a translation is the seed version plus both
  providers' pricing snapshot dates (FR-001, FR-012).

**Rationale**: Principle II puts linking tables that associate vendor services in Postgres, by
stable identifiers (the product keys of R2), not copied vendor attributes. Without Admin review
(clarification 3) nothing else writes mappings, so storing automatic matches would only cache
what the matcher derives from the current pricing data, and would go stale with it.

**Alternatives considered**: a JSON file read at start-up (simplest, but outside Principle II's
store for linking data, and a later Admin review would need the table anyway); storing automatic
matches (a cache with its own invalidation, for no current requirement, Principle VI).

## R4. Seed mappings are generated from 022's rules, never hand-written

**Decision**: `scripts/resolve_standard_architectures.py --provider gcp|azure` writes a third
output, `service_mappings_<provider>.json`. For every (architecture, component, figure) the AWS
rules and the provider rules share, it pairs the AWS SKU's product key with each target line's
product key. The quantity factor is the target quantity divided by the AWS quantity for that
figure (Glue DPU-hours → GCP vCPU-hours is ×4; one source can have several target lines, as
Lambda and Glue do). An omitted figure becomes a "no equivalent" row with 022's reason. When the
same source key maps to different targets in different architectures, or to the same target with
a different quantity factor or options, each distinct (target lines, factors, options) is kept
as a separate alternative with its 022 note (FR-008 then decides); identical pairs from several
architectures are kept once. Re-running against the same snapshots is byte-identical, as for the
other seed outputs.

**Round-trip test with alternatives**: where a source has one alternative, translating with the
defaults must reproduce 022 exactly. Where it has several, the test passes 022's own choice for
that architecture as an explicit pick, and checks separately that the default is the best
quality, then the lowest price.

**Rationale**: FR-016 and SC-006. 022's matches were reviewed once as rules; deriving the mapping
from the same rules keeps one source of truth and makes the round trip testable: translating an
AWS standard architecture to 022's regions reproduces 022's provider seed, service for service.

**Alternatives considered**: parsing the generated reports (Markdown, lossy); hand-writing the
mappings (a second copy of the same judgments that can drift).

## R5. How a source service is matched (FR-002 to FR-004, FR-008)

**Decision**, per source service and target provider:

1. A seed mapping for its product key → "seeded": resolve the target key in the chosen target
   region (R2). Not sold there → flagged and left out (FR-001). Several alternatives → the
   choice of FR-008. A seed "no equivalent" → flagged with 022's reason.
   *Amended 2026-11-20 (spec clarification):* where no seeded alternative is exact or close
   (partial, not sold, or no equivalent), step 2 runs as well. Its exact or close candidates are
   used instead, and the seed's other figures for the same service (same owner, service and
   category) are matched by step 2 too; otherwise the seed's result stands.
2. Otherwise 024's `find_candidates` in the target region → "automatic": exact and close
   candidates qualify; several qualifying → FR-008's default is the best quality, then the lowest
   price for the source's usage (each qualifying candidate is priced through the engine; the
   model never compares prices). Only partial candidates → "partial only": the service is left
   out unless the user chooses one (R7). None → flagged "no equivalent".
3. The source is already unpriceable in the original → flagged on both sides, not a saving
   (FR-014).

Usage is carried over by the seed's quantity factor, or by 024's `convert` (same kind of billing
unit only, FR-013). Machine sizes use 024's rule (at least the source's vCPU and memory; GCP
predefined shapes first).

**Rationale**: reuses 024's matcher, quality rules, usage conversion and sizing unchanged, and
adds only the seed lookup in front of them.

## R6. Cost: two architectures priced whole; the difference over what was matched

**Decision**: the original state and the translated state are each priced with
`calculate_architecture_price` (025's `price_state`) for the same duration (1 month, 31 days,
unless the user asks for another). Each mapping-table row shows the source's and the match's
amounts from those results. The **difference** (amount, percentage and main drivers) is computed
over the rows priced on both sides, as 024's comparisons do, and the summary says so whenever a
row is left out or unpriceable; both whole totals are shown too, labelled partial when anything
is missing. The main drivers are the three rows with the largest absolute difference. All figures
go to the model as figure references (023), never as numbers to repeat.

**Rationale**: SC-003 (engine figures to the cent) and FR-015 (a partial comparison is never
presented as the whole saving). Comparing like with like is 024's rule and keeps a left-out
service from appearing as a saving.

**Alternatives considered**: the difference of the whole totals (counts a left-out service as a
saving: the misleading answer US6 forbids).

## R7. "Chosen by you": a partial match needs an earlier offer

**Decision**: `find_translation` records, in its activity-log summary, each source whose only
candidates are partial ("offered"). `propose_translation` accepts a partial candidate only for a
source offered in an **earlier message of the same session**, so the user has had a turn to
choose; otherwise it returns an error telling the model to ask first. The row is marked
`chosen_by_user`, its differences are listed, and the cost answers name it (FR-004, FR-015). The
mapping data is unchanged.

**Rationale**: the app can't read intent, but it can make sure a partial match is never used in
the same answer that first found it. The activity log already records each operation's summary,
so no new state is needed. The golden conversation GC-7 checks the wording.

**Alternatives considered**: a flag the model sets (no guard at all); a per-session table of
offers (new storage for something the log already holds).

## R8. Two operations, references only

**Decision**:

- `find_translation(architecture, provider, regions?, term?)`: resolves the source (an `A…`
  reference from `list_my_architectures`, an `I…` from the public list, or the open one), checks
  the direction (FR-011) and size (100 items), chooses or guesses target regions (024's
  `region_guess`, FR-010), matches every service (R5), and returns `S…` sources with their status
  and `C…` candidates (quality, origin, differences, default) and what still needs the user.
- `propose_translation(architecture, provider, regions, term?, picks?, name?)`: builds the
  `Draft` (R1), prices it (R6), and saves the pending proposal. `picks` choose among a source's
  candidates (FR-008) or take an offered partial candidate (R7). A later call in the same session
  replaces the pending translation (US5), as 025's refinements do.

- `describe_translation(proposal?)`: the session's pending translation (or the latest one, or a
  `Q…` reference) as figure references: both totals, the compared difference and percentage, the
  drivers, the left-out and non-exact rows, and the caveats. Read-only; it re-reads the stored
  record and makes no new match or price. It is how a later message ("so which is cheaper?",
  GC-5) answers from engine figures, since figure references live for one message.

A translation fits in 023's round limit (8): find, propose, answer; a second message for answers
to the agent's questions repeats find (references live for one message), and a follow-up
question about the cost uses `describe_translation`.

**Rationale**: the same split as 024 (`find_matches` → `price_matches`) and 025 (`find_products`
→ `propose_*`): the app makes every match and figure; the model chooses by reference only
(Principle VII).

## R9. Stale translations

**Decision**: the proposal keeps the source state's fingerprint (025's `fingerprint`) and the
mapping data version (the seed version and both providers' pricing snapshot dates). When the
session is read, a pending translation whose source fingerprint, seed version or either snapshot
date no longer matches is shown as stale. Accepting a stale translation is refused (409)
with "The original or the pricing data changed since this translation. Ask me to translate it
again." and the proposal expires (FR-012). Translating again re-checks and re-prices.

**Rationale**: re-running the match is the only honest re-check (a changed source can have new
services that need choices), and the agent already does it in one message.

**Alternatives considered**: re-matching inside accept (the user would accept matches they never
saw).

## R10. Prompt, evaluation and paid runs

**Decision**: prompt `026.1` adds the translation rules (ask only for regions, term and choices;
never use a partial match the user didn't choose; name every caveat when asked which is cheaper;
state the term used for reserved sources). The golden conversations GC-1 to GC-7 become eval
cases `gc-32` to `gc-38`, scripted by default. Live runs use Claude Haiku 5.5 only, under the
paid-usage rules (estimate, approval, at most two runs per change). The first paid run also
includes 025's GC-20 and GC-21B, as recorded at 025's convergence.

## R11. Frontend

**Decision**: `AgentProposalView` shows a translation as: the mapping table (one row per source
service: source, match, quality, origin — "seeded", "automatic", "chosen by you" — differences,
assumptions, and each side's amount; left-out rows with their reason), then the cost difference
summary (both totals, the difference over matched rows with percentage, the main drivers,
partial labels and both snapshot dates), then 025's actions. `AgentProposalCard` names the
translation and its difference ("Prod Web → Azure: −$412.10 (−18.2%) on matched services"). No
new pages, no Admin UI.
