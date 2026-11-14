---

description: "Task list for 024 agent pricing questions and comparisons"
---

# Tasks: Agent Pricing Questions and Comparisons (Read-Only)

**Input**: Design documents from `specs/024-agent-pricing-questions/`

**Prerequisites**: plan.md, spec.md (US1–US6, clarifications 1–3), research.md (R1–R13),
data-model.md, contracts/ (`agent-operations.md`, `agent-api.md`, `results-pane-ui.md`),
quickstart.md

**Tests**: Included. Constitution Principle V requires tests first for pricing logic and for
Postgres reads and writes of user data, and forbids live models in the default run. Write each
test before its implementation and see it fail. Every agent test uses the scripted model client
(`backend/src/agent/clients/scripted.py`).

**Organization**: grouped by user story (spec.md).
- Paths are relative to the repo root.
- Backend commands run from `backend/` with `uv run`; backend tests need
  `PATH=/opt/homebrew/opt/postgresql@18/bin:$PATH`.
- Frontend commands run from `frontend/`.
- Never run a formatter on a whole folder. Format only the files you touch.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1–US6 from spec.md

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: package skeleton and test data.

- [X] T001 Create the package `backend/src/agent/matching/__init__.py` (docstring naming spec 024 and research R1–R7), and empty modules with docstrings: `profiles.py`, `quality.py`, `usage.py`, `regions.py`, `candidates.py`, `book.py`.
- [X] T002 [P] *(Done differently: no fixture rebuild was needed. `tests/helpers/agent.py` `combined_pricing_root()` copies the AWS default fixture and the 022 Azure/GCP standard fixtures, which already hold every product the cases use, into one temporary root; GC-4 uses a real GCP region with no data, asia-east1.)* Extend `backend/scripts/build_provider_fixtures.py` and regenerate the provider test fixtures with the rows the 024 cases need:
  - Azure `eastus`: Hot and Cool LRS block blob, a Premium SSD managed disk, a D4s_v5 Linux VM, PostgreSQL Flexible Server E4ds_v5, and a data transfer meter;
  - GCP `us-central1` and `us-east1`: Standard and Nearline storage, E2 core and RAM SKUs, Cloud SQL vCPU and RAM;
  - one storage product present in AWS `eu-west-1` and Azure `westeurope` but with no GCP rows in `europe-west1` (GC-4, missing pricing).
  Record in the script's docstring which case each row serves.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: data, figures, matching core, pricing of picks, the loop changes and the result
plumbing that every story uses.

**⚠️ CRITICAL**: complete this phase before any user story.

### Data

- [X] T003 Write `backend/tests/integration/test_migration_0011.py` (failing). Follow `test_migration_0010.py`. Upgrading from revision 0010 creates `agent_results` per data-model.md §1:
  - FKs to `agent_sessions` and `agent_messages`, both `ON DELETE CASCADE`;
  - `UNIQUE (session_id, seq)`;
  - the `kind` check;
  - the index on `session_id`.
  Deleting a session or a message removes its results. Downgrade drops the table.
- [X] T004 Write `backend/src/db/migrations/versions/0011_agent_results.py`, revising 0010's revision id, as plain DDL. Make T003 pass.
- [X] T005 Add the ORM class `AgentResult` to `backend/src/models/orm.py`, matching revision 0011. Its docstring holds the Principle II note from plan.md: a record of what was shown, never read as a price source.
- [X] T006 [P] Add the schemas from contracts/agent-api.md to `backend/src/models/schemas.py`:
  - `MatchQuality`, `AgentResultSide` (`id` = `<provider>:<region>`, provider, region, region_guessed, term), `AgentResultCell`, `AgentResultRow` (cells keyed by side id), `AgentResultTotal`, `AgentResultBasis`, `AgentResultOut` (`sides`, and totals keyed by side id), `AgentResultEvent`;
  - `AgentStatusEvent` gains optional `label`, `done`, `total`;
  - `AgentMessageOut.result_ids: list[uuid.UUID] = []` and `AgentSessionDetailOut.results: list[AgentResultOut] = []`;
  - `AgentResultsPreferences {split: float}` (0.3–0.75), with `WorkspacePreferences.agent_results: AgentResultsPreferences | None = None`;
  - `AgentOperationOut.outcome` allows `"timeout"`.
- [X] T007 [P] Extend `backend/tests/integration/test_preferences.py`: `workspace.agent_results.split` saves and reads back, and values below 0.3 or above 0.75 return `422`.

### Figures (research R7)

- [X] T008 [P] Extend `backend/tests/unit/test_agent_figures.py` (failing):
  - `FigureBook.add(Decimal("12.345"), "diff_pct", kind="percent")` renders `+12.3%`; negatives render `−4.0%`; `0` renders `0.0%`;
  - money figures still render `$1,234.56`;
  - a percentage the model types (`12%`) is still removed;
  - `footer` ignores percent figures when listing durations.
- [X] T009 Add `kind: Literal["money", "percent"] = "money"` to `Figure` and `FigureBook.add`, and render by kind in `backend/src/agent/figures.py`. Make T008 pass.

### Matching core (research R1–R4, R6, R7)

- [X] T010 [P] Write `backend/tests/unit/test_agent_profiles.py` (failing). `profile(item, provider)` gives function, category, specs and unit_kind for:
  - fixture rows of each provider: an AWS EC2 m5.large, an S3 Standard storage SKU, an RDS PostgreSQL instance;
  - an Azure D4s_v5, Hot LRS blob and Premium SSD;
  - a GCP E2 core SKU and Standard storage.
  An unrecognized attribute leaves the spec `None`, and an unknown unit gives `unit_kind="unknown"`.
- [X] T011 Implement `backend/src/agent/matching/profiles.py`: the `ProductProfile` dataclass, per-provider rule tables (AWS by `service_code`/`product_family`; Azure and GCP by catalog `kind`, then service name), and spec parsing from `CatalogItem.attributes`. Use `Categorizer` from `src/services/categories.py` for the category. Make T010 pass.
- [X] T012 [P] Write `backend/tests/unit/test_agent_quality.py` (failing), one test per row of the research R3 table:
  - exact (same function, unit and specs);
  - close (memory up to 2×, or the same class with different redundancy);
  - partial (different function in the same category, a different billing model, or unconvertible usage);
  - no equivalent (no candidate in the category).
  `differences` lists app-written facts. `lower(app_label, shown, reason)` accepts an equal or lower label, and raises `ToolError` for a higher label or a lowered label with no reason.
- [X] T013 Implement `quality(source, target) -> (label, differences)` and `lower(...)` in `backend/src/agent/matching/quality.py`. Make T012 pass.
- [X] T014 [P] Write `backend/tests/unit/test_agent_usage_conversion.py` (failing). Cover:
  - GB and GiB billing as the same unit kind (022's convention, research R4 note);
  - seconds, minutes and hours;
  - instance-hours to GCP `gcp_machine` options (vCPU and memory from the source; a custom size when the family allows it, else the smallest predefined size at least as large, with the difference listed);
  - Azure `azure_vm` options with the source OS;
  - an unconvertible pair (for example RPU-hours to slot-hours) returning `Unconvertible(reason)`, never a number;
  - `default_usage(function)` returns the research R4 defaults (1 TB-month storage, 730 h for VM, cache and DB, plus 100 GB for DB, 1 TB transfer, 1M requests) with a readable label, and `None` for a function with no default.
- [X] T015 Implement `backend/src/agent/matching/usage.py` (`convert(source_profile, quantity, unit, target_profile) -> Converted | Unconvertible`, and `default_usage(function)`, with factors and defaults as module constants). Make T014 pass.
- [X] T016 [P] Write `backend/tests/unit/test_agent_regions.py` (failing):
  - every region code in each provider's region list (the fixture snapshots and the current region lists) has an entry in `region_locations.json`;
  - every AWS region has a guess on Azure and on GCP or an explicit "no guess" (no match in its geography);
  - `region_guess("us-east-1", "azure")` returns `eastus` and `region_guess("us-east-1", "gcp")` returns `us-east1`, both with `guessed=True`;
  - a guess is only a region in `adapter.locations(snapshot)`;
  - a user-named region is returned unchanged with `guessed=False`;
  - an unknown region raises `ToolError` with the provider's closest region names.
- [X] T017 Create `backend/src/agent/matching/region_locations.json` (region code → `{city, country, geography}` for every region in the three providers' region lists, from the providers' published region pages; research R6). Implement `backend/src/agent/matching/regions.py`: the guess is the same city, then country, then geography, with ties to the lower code, filtered by the regions that have pricing data. Make T016 pass.
- [X] T018 [P] Write `backend/tests/unit/test_agent_match_book.py` (failing): sources get `S1…` and candidates `C1…` in insertion order; `get` of an unknown reference raises `ToolError`; a book is per message (a new book doesn't know old references).
- [X] T019 Implement `MatchBook`, `SourceProduct` and `Candidate` (data-model.md §2) in `backend/src/agent/matching/book.py`. Make T018 pass.
- [X] T020 Write `backend/tests/integration/test_agent_candidates.py` (failing), against the provider fixtures:
  - `find_candidates(sources, target_provider, region)` returns at most 5 candidates per source, ordered by quality, then spec distance, then SKU;
  - the same input gives the same output across two calls;
  - a source with nothing in its category is listed unmatched with a reason;
  - at most 4 adapter searches run at once (spy on the semaphore);
  - `progress(done, total, label)` is called once per source.
- [X] T021 Implement `find_candidates` in `backend/src/agent/matching/candidates.py`:
  - `adapter.search` via `asyncio.to_thread`, limit 200;
  - the `kind` preset where the function has one, else the per-function service-filter table;
  - profile, quality and conversion for each row;
  - deterministic ranking;
  - `asyncio.Semaphore(4)`;
  - an optional `hint` text per source.
  Make T020 pass.

### Pricing picks and results (research R5, R8)

- [X] T022 Write `backend/tests/integration/test_agent_compare.py` (failing). `price_comparison(reference_side, target_sides, duration, terms)`:
  - builds transient architectures with `build_transient_architecture`, priced by `calculate_architecture_price`;
  - every row amount equals a direct engine calculation of the same selection to the cent;
  - diff = target − reference and pct = diff / reference × 100, both from unrounded values; pct is null when the reference is 0;
  - a row unmatched, unconvertible or unavailable on either side has null amount, diff and pct, and marks both totals partial;
  - a term the candidate doesn't publish gives status `unavailable` with reason "term not offered";
  - parametrised over every term in FR-004 (AWS on demand; reserved 1y and 3y with no, partial and all upfront; GCP on demand, committed use 1y and 3y; Azure on demand, savings plan 1y and 3y, reservation 1y and 3y), with a fixture row that publishes it: the term maps to the adapter's `pricing_term`/`purchase_option` and the amount equals a direct engine calculation;
  - no `Architecture` row is added to the session (SC-007).
- [X] T023 Implement `backend/src/agent/compare.py`: `price_comparison(...) -> ComparisonOutcome`, holding sides (`<provider>:<region>`), rows with cells keyed by side, totals per side and the snapshot per provider, all as unrounded `Decimal`s, plus `pricing_term`/`purchase_option` mapping per provider for FR-004's terms. Make T022 pass.
- [X] T024 [P] Write `backend/tests/unit/test_agent_results_csv.py` (failing). The CSV from `write_csv(result)`:
  - starts with a UTF-8 BOM;
  - has the basis block (Comparison, Duration, Currency, one line per provider with region, "(guessed)", term and snapshot, then Assumptions), a blank row, and the table with the columns from contracts/agent-api.md;
  - writes amounts as plain `1234.56` with the same rounding as `format_usd` without the symbol, and pct with 1 decimal place;
  - leaves unavailable and unmatched cells empty, with a reason in `Status`, never `0`;
  - labels a partial total `Total (partial)`;
  - keeps names with commas, quotes or newlines valid when re-read with `csv.reader`, with the same rows and columns;
  - writes a text cell starting with `=`, `+`, `-`, `@`, a tab or a carriage return with a leading `'` (an architecture named `=HYPERLINK("http://x","y")` and a "where" label `+cmd` come out as text), while negative amounts, diffs and percentages stay plain numbers;
  - gives each side its own column group, and adds the region to the headers when one provider appears in two sides;
  - derives a filename `comparison-<slug>-<YYYY-MM-DD>.csv` that is ASCII and at most 80 characters.
- [X] T025 Implement `backend/src/agent/results.py`:
  - `create_result(session, agent_session, message, outcome, basis, kind) -> AgentResult`, with the next `seq`, a title and a summary line such as "14 rows · Azure total +12.4% (partial)";
  - `to_out(result) -> AgentResultOut`;
  - `write_csv(result) -> str` using `csv`, a shared `round_cents` from `figures.py`, and a `_safe_text` guard on every text cell against formula injection;
  - `csv_filename(result)`.
  Make T024 pass.

### Loop: references, results, time limit, progress (research R7, R8, R13)

- [X] T026 Extend `backend/tests/unit/test_agent_loop.py` (failing):
  - a `MatchBook` is created per message and reachable from `OperationContext.matches`;
  - an operation that creates a result causes an `AgentResultEvent` to be yielded right after its `operation` event;
  - an operation slower than `timeout_seconds` (a fake operation sleeping past a 0.2 s timeout) yields an `operation` event with `outcome="timeout"`, records it in `agent_operations`, sends the model the tool error "The operation took too long and was stopped", and the message still ends `done` (not failed);
  - `ctx.progress(3, 10, "Matching services")` yields `AgentStatusEvent(state="running_operation", label="Matching services", done=3, total=10)`, throttled to at most one every 250 ms.
- [X] T027 Implement the loop changes in `backend/src/agent/loop.py` and `backend/src/agent/operations.py`:
  - `OperationContext` gains `matches: MatchBook`, `agent_session`, `message`, `progress`, and a `results: list[AgentResult]` collector;
  - each `registry.run` runs under `asyncio.timeout(ctx.effective.timeout_seconds)`;
  - progress events go through an `asyncio.Queue` drained while the operation runs;
  - result events come from the collector after each operation.
  Make T026 pass.
- [X] T028 Extend `backend/tests/integration/test_agent_api.py` (failing):
  - a scripted stream that creates a result emits a `result` event whose body matches `AgentResultOut`;
  - `GET /agent/session` returns `results` and the message's `result_ids`;
  - after a stream that ends in `error`, the result created before it is still returned.
- [X] T029 Update `backend/src/api/agent.py`: serialize `AgentResultEvent` in `_stream`, add `results` and `result_ids` to the session detail, and document the `result` event in the route's OpenAPI responses union. Make T028 pass. Regenerate `frontend/src/api/generated/schema.d.ts` and update the OpenAPI snapshot in `backend/tests/contract/`.

### Frontend plumbing

- [X] T030 [P] Extend `frontend/src/lib/agentStream.ts` and its test: parse `result` events, and the `label`/`done`/`total` fields on `status` events, into typed events. Show "Matching services (12 of 20)…" in the status line of `frontend/src/components/agent/AgentConversation.tsx` when progress is present.

**Checkpoint**: foundation ready. Matching, pricing of picks, result storage and the stream all
work under test, with no new operation yet registered.

---

## Phase 3: User Story 1 - Compare a service category across providers (Priority: P1) 🎯 MVP

**Goal**: "How much cheaper is storage on Azure than GCP?" gets each provider's figure, the
difference and %, the basis and the snapshot dates, after at most three questions or stated
defaults.

**Independent Test**: for the benchmark category questions (gc-10, gc-11, gc-14), every figure
equals the engine's for the stated basis, and every answer states the basis and snapshot
dates.

### Tests for User Story 1

- [X] T031 [P] [US1] Write `backend/tests/integration/test_agent_compare_operations.py::test_search_products*` (failing):
  - `search_products(providers=["azure","gcp"], category="storage", function="object_storage")` returns up to 5 `C…` candidates per provider, with profile summaries and units;
  - regions are guessed and flagged when not given;
  - with `reference` set, each candidate carries quality and differences against it;
  - an unknown provider or category gives a `ToolError`.
- [X] T032 [P] [US1] Write `…::test_price_products*` (failing):
  - two picks and usage `1 TB` for `1_month` give per-provider money figures, a difference and a percent figure against the first pick, and a `result_id`;
  - `usage: "default"` applies `default_usage` for the picks' function, returns the default it used in the tool data and the basis, and a function with no default gives a `ToolError` asking for an amount;
  - the stored result's rows equal the engine's;
  - the activity log summary lists the resolved SKUs, the regions and `result_id`.
- [X] T033 [P] [US1] Add eval cases `backend/tests/agent_evals/cases/gc-10.yaml` (spec GC-1: asks about or states storage type, tier, redundancy, regions and amount), `gc-11.yaml` (GC-2: "use defaults" → every default and the region guesses are stated) and `gc-14.yaml` (GC-5: "and for 10 TB?" reuses the basis and says what changed), with scripted model turns. Add runner checks in `backend/tests/agent_evals/runner.py`:
  - `result_rows`: each stored row is recalculated through the engine for its basis and must match;
  - `states`: required basis phrases;
  - `max_questions`: at most 3 clarifying turns.

### Implementation for User Story 1

- [X] T034 [US1] Implement `search_products` and `list_regions` in `backend/src/agent/operations_compare.py`, registered in the 023 registry, with input models per contracts/agent-operations.md. Import the module from `backend/src/agent/operations.py` so the registry sees it. Make T031 pass.
- [X] T035 [US1] Implement `price_products`:
  - usage conversion through `matching/usage.py`;
  - pricing through `compare.price_comparison`;
  - figures through `ctx.figures`;
  - a result through `results.create_result` when there are 2 or more picks.
  Make T032 pass.
- [X] T036 [US1] Write prompt v024.1 in `backend/src/agent/prompt.py` (`PROMPT_VERSION = "024.1"`), covering:
  - which operation to use for category, architecture and single-price questions;
  - picking by `S…`/`C…` reference only;
  - asking at most 3 questions and offering defaults;
  - stating every default, guessed region and match quality;
  - writing figures only as `[[Fn]]`;
  - not restating the table row by row ("the table is shown beside you");
  - never recommending a provider.
  Add `backend/tests/unit/test_agent_prompt.py` (new) asserting `PROMPT_VERSION == "024.1"` and that the prompt names the five new operations and forbids recommending a provider. Make T033 pass.

**Checkpoint**: category comparisons work end to end with the scripted model. Results exist in
the API, and the pane comes in US6.

---

## Phase 4: User Story 2 - Compare the open architecture across providers (Priority: P1)

**Goal**: "What would this architecture cost on Azure (and GCP)?" gets per-service matches with
quality, both figures and the difference, then totals, with unmatched services listed and
partial totals labelled. Nothing is saved.

**Independent Test**: for each standard architecture compared with the other providers, every
matched service's figure equals the engine's for the stated match and usage, unmatched
services are listed, and a total that leaves any out is labelled partial (gc-15, gc-18).

### Tests for User Story 2

- [X] T037 [P] [US2] Write `…::test_find_matches*` (failing), with an AWS standard-architecture fixture open:
  - `find_matches(target_providers=["azure","gcp"])` returns every selection and connector service as `S…`, each with up to 5 candidates per target, the guessed regions and the unmatched list;
  - `category="storage"` limits it to storage services;
  - a target equal to the architecture's provider gives a `ToolError` naming it;
  - no open architecture gives a `ToolError`;
  - `hints` re-searches only the named source.
- [X] T038 [P] [US2] Write `…::test_price_matches*` (failing):
  - picks for every source across both targets create one result with three provider columns, rows in architecture order with `where`, and totals;
  - a `null` pick gives an `unmatched` row and partial totals;
  - `shown_quality` lower than the app's label is stored with its reason, and a higher one is a `ToolError`;
  - a reference from an earlier message is a `ToolError`;
  - the open architecture's rows and `updated_at` are unchanged afterwards (SC-007).
- [X] T039 [P] [US2] Add eval case `backend/tests/agent_evals/cases/gc-15.yaml` (spec GC-6: "What would this architecture cost on GCP?"). It runs `find_matches` then `price_matches`, with result rows equal to the engine's, unmatched services listed, and the total labelled partial. Add case `gc-18.yaml` for "on the other two clouds", with three providers in one result. Add runner checks `partial_total` and `operations_within_rounds` (at most 6 model rounds).

### Implementation for User Story 2

- [X] T040 [US2] Implement `find_matches` in `backend/src/agent/operations_compare.py`:
  - sources from the open architecture (reuse `_open_architecture` and `_selection_labels` from `operations.py`);
  - `adapter.describe` for profiles;
  - `find_candidates` per target with `ctx.progress`;
  - references in `ctx.matches`.
  Make T037 pass.
- [X] T041 [US2] Implement `price_matches`:
  - the reference side from the architecture's own selections, priced as-is;
  - target sides from the picks;
  - quality lowering through `quality.lower`;
  - a result of kind `architecture_comparison` titled "<architecture>: AWS vs Azure, GCP".
  Make T038 and T039 pass.
- [X] T042 [US2] Handle the spec edge cases in `find_matches`/`price_matches` and the prompt: the architecture already on the target provider ("already on that provider", with the current total offered instead), and an architecture changed since the last answer (sources are always read fresh, and the answer says it used the architecture as it is now). Add a test for each to `test_agent_compare_operations.py`.

**Checkpoint**: architecture comparisons work end to end, scripted, within the round limit.

---

## Phase 5: User Story 3 - Be honest about products that aren't equivalent (Priority: P1)

**Goal**: non-equivalent products are named as such, with the closest match, the quality and
the differences, never as like for like.

**Independent Test**: for benchmark questions whose products differ (gc-12), every answer names
the match quality and at least one concrete difference, and the stored labels are the app's
(or lower).

- [X] T043 [P] [US3] Add eval case `backend/tests/agent_evals/cases/gc-12.yaml` (spec GC-3: a tier with no counterpart, for example GCP Archive versus an Azure tier): the answer says there's no direct counterpart, shows the closest match and lists a difference. Add the runner check `qualities` (the expected label per source in the stored result) and a check that the answer text contains a match-quality word.
- [X] T044 [P] [US3] Add a units case to `test_agent_compare_operations.py`: products billed in GB versus GiB, or per second versus per hour. The stored basis states the converted usage and the factor comes from `usage.py`; the model's arguments carry no converted numbers.
- [X] T045 [US3] Make sure `differences` and the conversion note (`converted_from`, `factor`) reach the model's tool data and the stored result cells, in `backend/src/agent/operations_compare.py`. Extend the prompt in `backend/src/agent/prompt.py` so the agent always names the quality and at least one difference for anything below exact. Make T043 and T044 pass.

**Checkpoint**: honesty rules are enforced by the app and checked by the evals.

---

## Phase 6: User Story 4 - Missing data is never estimated (Priority: P1)

**Goal**: a provider, region, product or term that can't be priced is shown as unavailable,
with no figure, difference or %.

**Independent Test**: with no GCP pricing in the chosen region (fixture from T002), the
comparison shows the other providers and says GCP can't be priced there (gc-13).

- [X] T046 [P] [US4] Add eval case `backend/tests/agent_evals/cases/gc-13.yaml` (spec GC-4): pricing is missing for one provider in the chosen region. Add the runner check `unavailable`: the named provider has no figure, difference or % in either the text or the result, and the text says it can't be priced there.
- [X] T047 [P] [US4] Add tests to `test_agent_compare_operations.py`:
  - a term one provider doesn't publish gives `unavailable` "term not offered", and the tool data lists the terms it does publish;
  - a provider whose snapshot is stale or failed shows its snapshot date and status and doesn't block the others (Principle I);
  - a comparison where nothing could be priced creates no result.
- [X] T048 [US4] Implement the gaps in `backend/src/agent/compare.py` and `backend/src/agent/operations_compare.py`:
  - `offered_terms` in the tool data;
  - snapshot status per provider from `get_active_snapshot`;
  - skip result creation when no row is priced.
  Make T046 and T047 pass.

**Checkpoint**: Principle I gaps are explicit everywhere.

---

## Phase 7: User Story 6 - See and save comparison results (Priority: P1)

**Goal**: results appear in a Results pane to the right of the conversation, with a draggable
divider saved in preferences, cards in the conversation, ◀ ▶ through the session's results, CSV
download, stacking below 700 px, and persistence with the session.

**Independent Test**: after two comparisons in a session:
- the pane shows the second, steps back to the first, and selecting the first card shows it;
- each downloaded CSV contains exactly the rows and figures shown, with the basis, and empty
  marked cells for unavailable prices;
- after a reload, the cards and results are there.

### Tests for User Story 6

- [X] T049 [P] [US6] Write `backend/tests/integration/test_agent_results_api.py` (failing). `GET /agent/session/results/{id}/csv`:
  - returns `200 text/csv; charset=utf-8` with a BOM and `Content-Disposition` carrying the filename;
  - returns the same rows and figures as `GET /agent/session`'s result;
  - returns `404` for another user's result and for a result of an expired session;
  - returns `403` for a guest.
- [X] T050 [P] [US6] Write `frontend/src/lib/agentResults.test.ts` (failing):
  - the pane-state reducer: hidden with no results; `result` arrival opens it and selects the new one; close hides it; selecting a card opens it on that result; prev and next stop at the ends; a new session resets;
  - formatting: amounts through the app's USD formatter, pct with 1 decimal place and a sign;
  - `downloadResultCsv(id)` fetches with the auth header and saves using the server filename (mock `fetch` and `URL.createObjectURL`).
- [X] T051 [P] [US6] Write `frontend/src/components/layout/VerticalSplit.test.tsx` (failing):
  - a separator with `aria-orientation="vertical"` and `aria-valuenow`;
  - drag and the arrow keys (5% steps) clamp to 30–75%; Home and End go to the limits;
  - `onCommit` fires on release with the share;
  - below 700 px of width (mocked `ResizeObserver`) the second child renders below the first with no separator.
- [X] T052 [P] [US6] Write `frontend/src/components/agent/AgentResultsPane.test.tsx` (failing), per contracts/results-pane-ui.md:
  - the header has ◀ ▶, "Result k of n", Download CSV and Close results, all with accessible names;
  - the basis lines show "(guessed)";
  - the table has a caption, per-provider product and amount columns, a quality badge whose tooltip lists the differences, and diff and %;
  - unavailable, unmatched and unconvertible cells show their words and no number;
  - the footer shows "Total (partial)" and the "Not compared:" list;
  - a download failure shows "Couldn't download the result.".
- [X] T053 [P] [US6] Extend `frontend/src/components/agent/AgentPanel.test.tsx` (or create it):
  - with no results only the conversation shows;
  - a streamed `result` opens the pane beside it and adds a card ("Show result: <title>") under the agent message;
  - the card for the shown result has `aria-current="true"`;
  - session detail with results restores the cards and opens the pane on the latest result (spec US6 scenario 8);
  - the divider's commit saves `workspace.agent_results.split` through the preferences store.

### Implementation for User Story 6

- [X] T054 [US6] Add the route `GET /agent/session/results/{result_id}/csv` to `backend/src/api/agent.py`. It uses `results.write_csv` and `csv_filename`, applies the owner-session check, and is documented with a `text/csv` response in OpenAPI. Regenerate `frontend/src/api/generated/schema.d.ts`. Make T049 pass.
- [X] T055 [P] [US6] Implement `frontend/src/lib/agentResults.ts` (pane reducer, formatters, `downloadResultCsv` reusing the save pattern in `frontend/src/lib/exportFilename.ts`) and add `getAgentResultCsv` to `frontend/src/api/client.ts`. Make T050 pass.
- [X] T056 [P] [US6] Implement `frontend/src/components/layout/VerticalSplit.tsx`: two children, the separator, pointer and keyboard handling, `ResizeObserver` stacking at 700 px, and `split`/`onCommit` props. Make T051 pass.
- [X] T057 [US6] Implement `frontend/src/components/agent/AgentResultsPane.tsx` (header, basis, table with a sticky header, footer) and `frontend/src/components/agent/AgentResultCard.tsx`. Make T052 pass.
- [X] T058 [US6] Wire it up in `frontend/src/components/agent/AgentPanel.tsx` and `AgentConversation.tsx`:
  - `VerticalSplit` with the conversation and the pane;
  - the reducer fed by stream `result` events and the session detail;
  - cards under agent messages by `result_ids`;
  - the split read from and saved to `workspace.agent_results` in `frontend/src/lib/preferences.ts`.
  Make T053 pass.
- [X] T059 [US6] Write `frontend/e2e/agent-results.spec.ts`, using the scripted provider as in `frontend/e2e/agent.spec.ts`:
  - ask an architecture comparison; the pane opens with the table and a card appears;
  - Download CSV saves a file whose rows match the table;
  - a second comparison shows "Result 2 of 2" and ◀ goes back;
  - drag the divider, wait for the preference save request (register `waitForRequest` before the action, then await `.response()`), reload, and the split is kept, with the cards back and the pane open on the latest result;
  - split the centre column so the Agent tab is narrow, and Results stacks below.

**Checkpoint**: the full user-facing flow works with the scripted model.

---

## Phase 8: User Story 5 - Look up a specific price (Priority: P2)

**Goal**: a single named product, region and term gets its figure with the basis, in the
conversation only.

**Independent Test**: for the benchmark single-price questions (gc-17), every figure equals the
engine's for the stated basis, and no result is created.

- [X] T060 [P] [US5] Add eval case `backend/tests/agent_evals/cases/gc-17.yaml` (spec GC-8: "What's the on-demand price of an m5.large in eu-west-1 per month?"): the figure equals the engine's, the basis and snapshot are stated, and the runner check `no_result` (no `agent_results` row) passes.
- [X] T061 [P] [US5] Add tests to `test_agent_compare_operations.py`: `price_products` with one pick returns one figure and no `result_id`; a product name matching several catalog entries returns several candidates from `search_products`, so the agent asks which one or states its choice.
- [X] T062 [US5] Confirm that the single-pick path in `price_products` creates no result, and extend the prompt guidance for ambiguous names in `backend/src/agent/prompt.py`. Make T060 and T061 pass.

**Checkpoint**: all six stories work.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T063 [P] Add eval case `backend/tests/agent_evals/cases/gc-16.yaml` (spec GC-7: "Which cloud is best?"). The agent doesn't recommend a provider and offers a specific comparison, checked with `not_contains` for recommendation phrases ("you should choose", "I recommend", "best choice"). Add `no_recommendation` to the runner.
- [X] T064 [P] Add the remaining edge cases from spec.md to `test_agent_compare_operations.py` or the eval cases:
  - a region that doesn't exist on a provider;
  - "compare everything" (the agent asks which categories);
  - several regions on one provider (one column group per provider and region in the same result, data-model.md §3 Side);
  - a request to build or save the comparison as an architecture (declined, pointing to agent-04's future feature);
  - a new session starting with no results.
- [X] T065 Run the scripted golden set and the whole backend suite (`uv run pytest`), then the frontend unit tests (`npm test`) and the full e2e (`npx playwright test`), three times in a row for e2e. Fix any failures.
- [X] T066 *(Run 2026-11-13: Claude Sonnet 5.5 passed 14 of 18 cases and llama3.1 5 of 18; see the completion report. Failing cases were reported, not loosened.)* Make the live evaluation read `AGENT_ANTHROPIC_API_KEY` the way the app does: in `backend/tests/agent_evals/test_golden_live.py`, take the key from the process environment, else from `settings.agent_anthropic_api_key` (which loads `backend/.env`), so the key lives in one place. Never print or log it; the skip message names only the variable. Add a unit test with a temporary `.env` and a monkeypatched environment, checking environment first, then `.env`, then a skip. Update the live-eval note in `docs/development.md` to say `backend/.env` is enough. Then run the opt-in live evaluation on the two SC-006 models, `AGENT_EVAL_MODELS="ollama:llama3.1,anthropic:claude-sonnet-5-5"` (the owner puts the Anthropic key in `backend/.env`, which is gitignored and never committed), and record the pass counts per case and model from `backend/agent-eval-report.md` in the completion report. If a case fails on a model, report it with the transcript excerpt rather than loosening the case. Don't commit the report.
- [X] T067 [P] Update `docs/features/agent.md`: what the agent can compare, the basis, match quality and its rules, unavailable prices, the Results pane (layout, cards, stepping, stacking), CSV download and its layout, the operation time limit and the progress text. Also update the activity-log section for the new operations.
- [X] T068 [P] Update `docs/features/workspace-and-preferences.md` with the saved results split (`workspace.agent_results.split`), and `docs/features/README.md` if its index lists agent capabilities.
- [X] T069 [P] Add the lines under `Unreleased` in `CHANGELOG.md`: comparisons by category and for the open architecture against one or both other providers, single prices, match quality, the Results pane with CSV download, and the operation time limit with progress.
- [X] T070 *(Done as an automated walk-through: the e2e covers the pane, cards, stepping, download, divider and stacking; `find_matches`/`price_matches` were timed and their matches reviewed against the real pricing data: 0.2–0.7 s for the standard architectures against two providers, 16 services in 0.4 s. That review found and fixed the matching rules in research R1's addendum.)* Walk through `specs/024-agent-pricing-questions/quickstart.md` §3 with a local model. Record the `find_matches` `duration_ms` seen for a 20-service architecture (the 10 s target, research R13) in the completion report.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: after Setup. It blocks every story.
- **US1 (Phase 3)**: after Phase 2.
- **US2 (Phase 4)**: after Phase 2. It shares `operations_compare.py` and the prompt with US1, so run it after US1 or coordinate edits to those two files.
- **US3, US4 (Phases 5–6)**: after US1 and US2, which they harden.
- **US6 (Phase 7)**: after Phase 2 for the API and pane (it can use results from tests). For the e2e (T059), after US2.
- **US5 (Phase 8)**: after US1, which provides `price_products`.
- **Polish (Phase 9)**: after the stories it covers.

### Within each story

Tests first and failing → implementation → the story's checkpoint.

### Parallel opportunities

- Phase 1: T002 alongside T001.
- Phase 2: T006, T007, T008, T010, T012, T014, T016, T018 and T024 are separate files; T030 is
  frontend and separate.
- US1: T031, T032 and T033 together.
- US2: T037, T038 and T039 together.
- US3 and US4 tests: T043, T044, T046 and T047 together.
- US6: T049–T053 together; T055 and T056 together; the frontend work can run alongside US3 and
  US4.
- US5: T060 and T061 together.
- Polish: T063, T064 and T067–T069 together.

## Parallel Example: User Story 6

```text
Task: "T049 results API tests in backend/tests/integration/test_agent_results_api.py"
Task: "T050 pane reducer and download tests in frontend/src/lib/agentResults.test.ts"
Task: "T051 VerticalSplit tests in frontend/src/components/layout/VerticalSplit.test.tsx"
Task: "T052 Results pane tests in frontend/src/components/agent/AgentResultsPane.test.tsx"
```

## Implementation Strategy

### MVP first

1. Phases 1 and 2.
2. Phase 3 (US1): category comparisons, verified by the scripted golden conversations.
3. Phase 7 (US6) far enough to see the result in the pane (T054–T058), so the MVP is visible
   in the app.
4. Stop and validate with a local model (`AGENT_MODEL=llama3.1`).

### Incremental delivery

US2 (architecture comparisons) → US3 and US4 (honesty and gaps) → the rest of US6 (e2e) →
US5 (single prices) → Polish. The agent stays off by default throughout, so the app is
unchanged for users without it.
