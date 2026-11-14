# Research: Agent Pricing Questions and Comparisons (Read-Only)

**Feature**: 024-agent-pricing-questions | **Date**: 2026-11-13

All decisions build on 023's agent package (`backend/src/agent/`): the registry of typed
operations, the figure book, the loop (6 rounds), the activity log and the SSE stream.

## R1. Candidate finding: one batch operation over the provider adapters

**Decision**: a new module `src/agent/matching/` finds candidates for many source products in
one call (clarification 1).

- **Source products**: the open architecture's selections, described through
  `adapter.describe()`. For a category question there's no source: the agent first searches
  one provider, and the product it picks becomes the reference.
- **Target search**: `adapter.search()` in the target region.
  - Azure and GCP use their `kind` preset (`vm`, `block_storage`, `object_storage`,
    `managed_db`, `data_transfer`) where the source's function has one.
  - Otherwise the search uses a per-function table of service filters, for example storage
    → Cloud Storage / Storage, or managed DB → Cloud SQL / Azure Database for ….
  - Up to 200 rows are searched per source.
- **Ranking**: each target row gets a profile (R2), a quality (R3) and a specification
  distance. Rows are sorted by quality, then distance, then SKU, and the top 5 are kept.
  The order is deterministic (FR-009a).
- **Concurrency**: searches run with `asyncio.to_thread` under a semaphore of 4, so a
  20-service architecture against 2 targets (40 searches) stays within seconds.

**Rationale**:
- This reuses the provider adapters (Principle III) and keeps the model to one structured
  choice. It fits the 6-round limit: describe, then find, then price is 2–3 rounds.

**Alternatives considered**:
- Reuse 022's `match_rules_*`. Rejected: they're per-component rules for the four standard
  architectures, not a general finder. 022 R10 already left mapping data to agent-04.
- Let the model call `search` per service. Rejected by clarification 1 (round limit).

### R1 addendum: rules found against the real catalog (2026-11-13)

Checked against the full pricing data, not just the fixtures:
- **Narrowed searches.** Azure lists about 2,100 VMs and 1,300 managed-database rows in one
  region, more than one 1,000-row search holds. So each source's search is narrowed by its
  specs (`targeted_searches`):
  - VMs by vCPU count in the size name, and on AWS in the `vcpu` attribute;
  - databases by engine;
  - blob operations, load balancers, DNS, transfer kind and Kubernetes by their product names.
- **Never offered as a match** (`EXCLUDED_WORDS`): terms or discounts sold as their own SKU
  (commitments, committed use, reservations, savings plans), spot or preemptible capacity,
  Cloud Services, dedicated hosts, licences, and free, developer, read-replica, backup and
  extended-support variants. AWS EC2/RDS rows that aren't shared, plain, used capacity are
  also excluded.
- **Ranking.** Niche variants (Enterprise Plus, dual- or multi-region, premium, internal,
  cross-regional, "always ready", tagging, custom) rank after the plain product. So does a
  product that names another part of the world than the target region (for example "from
  Delhi" for us-east4).
- **Speed** on the real data: `find_matches` takes 0.2–0.7 s for the standard architectures
  against two providers (16 services: 0.4 s), well under the 10 s target.

## R2. Product profile

**Decision**: `profile(item, provider) -> ProductProfile` with these fields.

- **function**: `vm`, `object_storage`, `block_storage`, `file_storage`, `managed_db`,
  `cache`, `data_transfer`, `load_balancer`, `dns`, `serverless`, `queue`, or `other`.
  - AWS uses `service_code` and `product_family`.
  - Azure and GCP use the catalog `kind`, then service-name rules.
- **category**: from the existing `Categorizer` (019), one of compute / storage / database /
  networking.
- **specs** (where the catalog attributes carry them): `vcpu`, `memory_gib`, `os`, `engine`,
  `storage_class` (hot/standard, cool/nearline, cold/coldline, archive), `redundancy`
  (local/zonal/regional/geo), `ha`, `media` (ssd/hdd).
  - Added against the real catalog: `purpose` (general, compute, memory, storage,
    accelerated, confidential), `burstable`, `transfer` (internet, inter-region or other),
    `visibility` (public or private DNS), and `lb_layer` (application, network, gateway).
- **unit_kind** (R4): `hour`, `gb_month`, `gb`, `request`, `vcpu_hour`, `gib_hour`, and so
  on, or `unknown`.

The rules live in one table per provider in `matching/profiles.py`, in the style of
`units.py`. An attribute that isn't recognized leaves the spec empty. It's never guessed.

**Rationale**: quality and usage conversion both need the same few comparable facts.
Explicit tables are reviewable, as in 014 and 022.

## R3. Quality rules (clarification 3, FR-009b)

**Decision**: `quality(source, target) -> (label, differences)`.

| Label | Rule |
|---|---|
| exact | same function, same unit_kind, and every spec both sides have is equal |
| close | same function, same unit_kind (or one simple scale, R4), and specs differ by at most one size step or one minor attribute (e.g. vCPU equal but memory up to 2× larger; same storage class with different redundancy) |
| partial | same category, a major spec difference (vCPU, less or over twice the memory, machine purpose, OS, engine, access tier, kind of transfer, DNS zone type, load balancer type), different function or a different billing model (for example per-instance versus per-vCPU/GiB, provisioned versus serverless), or usage that can't be converted |
| no equivalent | no candidate in the same category |

- `differences` is a list of short app-written facts, for example "memory 16 GiB vs 8 GiB",
  "redundancy zonal vs local" or "billed per vCPU-hour and GiB-hour, not per instance-hour".
- The agent may send `shown_quality` below the app's label, with a `reason`. A higher label
  is rejected as a tool error.

**Rationale**: the app is the arbiter, so labels are testable and can't be inflated
(US3, SC-005).

## R4. Usage conversion: the 022 guiding rule

**Decision**: a source quantity is converted to the target's billing unit only when both bill
the same kind of unit and at most a fixed scale is needed.

- **Allowed scales**: none beyond the adapters' own block normalisation (per-10K, per-1M),
  plus GCP machines (instance-hours priced as vCPU × core rate + GiB × RAM rate by the
  existing `gcp_machine` options).
  - *Implementation note (2026-11-13)*: GB and GiB are treated as the same billed unit, not
    scaled by 1.073741824. That's the convention 022's reviewed standard architectures use
    (S3 2000 GB-months → GCP 2000 GiB-months), and AWS bills "GB" in binary gigabytes.
    Scaling here would make 024's comparisons disagree with the seeded equivalents.
- **Anything else** (for example RPU-hours to slot-hours) can't be converted. The candidate
  stays, but its quality is at most partial and its price is "unavailable: usage can't be
  converted". No figure is shown (FR-011).
- **GCP machines and Cloud SQL**: priced with `gcp_machine` options (vCPUs, memory GiB,
  RAM SKU), as in 022 R6. The size is the source's vCPU and memory exactly when the family
  allows custom sizes. Otherwise it's the smallest predefined size at least as large, and the
  difference is listed.
- **Azure VMs**: `azure_vm` options with the source OS.
- The conversion factors are app code in `matching/usage.py`, never the model's (US3
  scenario 2).
- **Default usage** for category questions with no amount given is one table per function in
  `matching/usage.py`, for example:
  - object, block and file storage: 1 TB-month;
  - VM, cache and managed DB instance: 730 hours a month, plus 100 GB of storage for a
    managed DB;
  - data transfer: 1 TB;
  - requests: 1 million.
  `price_products` takes `usage: "default"`, applies the table and returns the default it
  used, so the agent states it (FR-006). The model never makes up a default amount.

**Rationale**: owner rule from 022 ("no complex logic to force a mapping") and Principle I.

## R5. Pricing the picks: transient architectures through the engine

**Decision**: `price_matches` builds one transient architecture per provider with
`build_transient_architecture` (008/020): the source side from the open architecture's own
selections, and each target from the picks with the converted quantities and the chosen
term. Each one is priced with `calculate_architecture_price`.

- Differences are `target − source` and percentages are `(target − source) / source × 100`,
  both from unrounded engine values. Percent is shown to 1 decimal place and is left out
  when the source amount is 0.
- Totals are labelled partial when any row on either side is unmatched or unpriceable
  (FR-012).
- The open architecture itself is never touched, so SC-007 holds by construction.

**Rationale**: the exact code path the Pricing tab uses, with no new arithmetic on prices
(Principle I).

## R6. Region guesses

**Decision**: a `region_guess(source_region, target_provider)` table in
`matching/regions.py`. The app has no location metadata for regions
(`src/pricing_data/regions.py` lists only codes, plus Azure display names), so:
- `backend/src/agent/matching/region_locations.json` is a reviewed table of every region code
  in the three providers' current region lists → `{city, country, geography}`, taken from the
  providers' published region pages. It's checked in and covers only regions that have
  pricing data.
- The guess picks the same city, then the same country, then the same geography; ties go to
  the lower region code.
- A region with no match in its geography has no guess. The agent then asks.
- A test fails when a region in any provider's region list is missing from the table, so new
  regions get added deliberately.

- it maps each provider's region to the nearest region on each other provider, by the
  geography and city the app's region lists already carry;
- it only proposes regions that have pricing data (`adapter.locations`);
- every guessed region is returned with `guessed: true`, and the agent must state it
  (FR-007).

A user-named region always wins.

**Rationale**: the spec rules out curated region matching as a feature, but the agent needs
a deterministic first guess. A small static table of nearest regions, without equivalence
claims, satisfies "a guess, stated".

**Alternative considered**: let the model guess. Rejected because it's non-deterministic and
untestable.

## R7. Match and figure references

**Decision**:
- `find_matches` returns sources as `S1…` and candidates as `C1…`, held in a per-message
  `MatchBook` next to the `FigureBook`. The model picks by reference only, so it can't name a
  SKU that wasn't a candidate. Picks of unknown references are tool errors.
- A user's correction ("use Premium SSD instead") means running `find_matches` again with a
  `hint`. The hint is a search text added to that source's target search, so corrections still
  come from catalog candidates.
- Percentages become figures too: `FigureBook.add(..., kind="percent")` renders `+12.3%`, so
  the existing filter still removes any percentage the model types itself.

## R8. Results: stored records, pushed by event, downloadable as CSV

**Decision**:
- **Storage**: a new table, `agent_results` (data-model.md), cascades from the session and
  the message. It stores what was shown: the basis, columns, rows, totals and each provider's
  snapshot date and revision.
  - Amounts are kept as unrounded decimal strings. Display and CSV both round to 2 decimal
    places with the same function.
  - A result is a record of an answer, like the message text 023 already stores. It's never
    read back as pricing input, so it's compatible with Principle II (see the plan's
    Constitution Check).
- **Stream**: the stream gains a `result` event, sent as soon as `price_matches` creates a
  result. `GET /agent/session` returns `results` and each agent message's `result_ids`.
- **CSV**: generated on the server by `GET /agent/session/results/{id}/csv`, with Python's
  `csv` module, a UTF-8 BOM for spreadsheet tools, and `Content-Disposition` with a filename.
  - The file starts with a basis block of key and value rows, then a blank row, then the
    table. Numbers are plain (`1234.56`), with no `$` or thousands separators.
  - Percent cells are plain numbers in a `diff_pct` column.
  - Unavailable cells are empty, with a `status` column reading `unavailable: <reason>`.
  - Partial totals are labelled `Total (partial)`.
- **Download in the browser**: the route needs the Bearer header, so the frontend fetches it
  and saves the blob through a temporary object-URL link (the existing export pattern in
  `exportFilename.ts`).

**Rationale**: one formatting implementation, testable in pytest (SC-008). Generated types
cover the JSON shape (Principle IV).

**Alternative considered**: build the CSV in the browser from the JSON. Rejected because it
would mean two formatting paths for the same numbers.

## R9. Category comparisons and single prices (US1, US5)

**Decision**: two more operations.
- `search_products(providers[], category, region per provider?, text?, specs?)` returns
  candidates per provider (`C…` references) with profiles, using region guesses where none
  are given. When a reference product is picked, quality is computed against it.
- `price_products(picks[], usage, unit, duration, terms)` prices one or more picked
  candidates, converting the stated usage per R4.
  - With two or more providers it creates a result and returns difference figures against
    the first provider named (the reference).
  - With one provider it returns only the figure (single-price lookup, no result).

**Rounds**: search, then price, is 2 rounds (3 with a clarifying turn in between).

## R10. Pricing terms

**Decision**: picks carry a per-provider term from FR-004's list, mapped onto the existing
`pricing_term` and `purchase_option` values of each adapter.
- A term a candidate doesn't publish (`price_types` for Azure and GCP; units lookup for AWS)
  makes that row unavailable with the reason "term not offered". The agent then offers the
  terms it does publish (US4 scenario 2).

## R11. Results pane layout

**Decision**:
- `AgentPanel` (the Agent tab body) becomes a horizontal two-column layout:
  - the conversation on the left, `AgentResultsPane` on the right;
  - a vertical divider between them, keyboard-adjustable, as an ARIA separator;
  - the split is 0.3–0.75 of the width, default 0.45 for the conversation.
- A `ResizeObserver` on the tab body stacks the two (results below) when the body is under
  700 px wide.
- The split is saved as `workspace.agent_results.split` in account preferences, so
  `WorkspacePreferences` gains an `AgentResultsPreferences`.
- Pane state (open, current result) is session-local UI state, not saved. A new result opens
  the pane and selects it.

**Rationale**: matches the owner's layout (spec FR-018). A dedicated small divider is enough;
`SplitTabPane` is a vertical stacker for tabs and isn't reused for this.

## R13. Operation time limit and progress

**Decision**:
- **Time limit**: the loop runs each operation under `asyncio.timeout` using the existing
  `timeout_seconds` setting (Admin → Agent Settings, default 60 s). There's no new setting.
  - On overrun, the operation's thread work is abandoned, since DuckDB calls run in
    `to_thread` and can't be interrupted; the semaphore bounds how many can pile up.
  - The activity log records `outcome: "timeout"`.
  - The model gets the tool error "The operation took too long and was stopped", tells the
    user it couldn't finish, and offers a smaller comparison, for example one category.
  - The message completes normally. It isn't a failed message, and it doesn't stop the loop.
- **Progress**: `OperationContext` gains `progress(done, total, label)`, a callback that puts
  a status event on the loop's queue. The stream relays it as `status` with
  `{state: "running_operation", label: "Matching services", done: 12, total: 20}`.
  - `find_matches` reports after each source product. Updates are throttled to at most one
    every 250 ms.
  - Other operations don't report progress, and the panel shows the existing status text.
- **Measuring**: the 10 s target for `find_matches` is checked by hand in the quickstart and
  logged as `duration_ms` in the activity log. It isn't a test assertion, because machine load
  would make it flaky.
  - A unit test checks the time limit with a deliberately slow fake operation and a short
    timeout.

**Rationale**:
- Before this, operations had no time limit, only model calls did. A hung catalog query would
  hang the message, the same symptom as 023's busy-session bug.
- Progress makes a slow but working match distinguishable from a hang.

**Alternatives considered**:
- A separate operation timeout setting. Rejected: one more Admin field with no clear need
  (Principle VI).
- Raising the 10 s target. Rejected: it isn't a limit, and model rounds dominate the total
  wait.

## R12. Prompt and evaluation

**Decision**:
- **Prompt v024.1** adds:
  - when to use each operation;
  - pick by reference;
  - state assumptions, guesses and match quality in prose, but don't restate every table
    row ("the table is shown beside you");
  - never recommend a provider;
  - ask at most 3 questions, and offer defaults.
- **Eval cases** `gc-10…gc-17.yaml` correspond to spec GC-1…GC-8. They are scripted by
  default and can run live with `AGENT_EVAL_MODELS`. New runner checks:
  - `result_rows` (each row's figures equal a fresh engine calculation for the stored basis);
  - `qualities` (expected label per source);
  - `no_result` (single price);
  - `partial_total`;
  - `unavailable` (no figure for the named provider).
- **Fixtures**: the provider fixtures (`build_provider_fixtures.py`) gain the few Azure and GCP
  rows the cases need. GC-4 (missing pricing) uses a region present in one provider's fixture
  only.
