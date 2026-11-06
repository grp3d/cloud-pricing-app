---

description: "Task list for 020: Provider Icons and Price Change Fixes"
---

# Tasks: Provider Icons and Price Change Fixes

**Input**: Design documents from `specs/020-provider-icons-connector-fixes/`

**Prerequisites**:
- [plan.md](plan.md) and [spec.md](spec.md)
- [research.md](research.md) (R1 to R7)
- [data-model.md](data-model.md) and [contracts/api.md](contracts/api.md)
- [quickstart.md](quickstart.md)

**Tests**: Required. Constitution Principle V makes tests mandatory, written first, for pricing logic, the snapshot re-pricing path, Price Change decisions, stored-record type guards, icon resolution and the icon generator's matching. The fallback tile's look is UI-only, so its tests may follow the code.

**Scope**: User Story 1 (Price Change) and User Story 2 (icons) only. The spec's "Deferred: Connector Updates" section has no tasks here.

**Organization**: Tasks are grouped by user story. Each story can be built, tested and shipped on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 or US2
- Paths are from the repository root (`backend/`, `frontend/`)

## Shared notes

- **Backend tests** need `export PATH=/opt/homebrew/opt/postgresql@18/bin:$PATH` and the
  `cloud_pricing_test` database at head. No new migration in this feature.
- **Regenerating API types:**
  1. Dump `app.openapi()` with `PRICING_DATA_URI=file://$PWD/tests/fixtures/pricing_parquet`.
  2. Run `npx openapi-typescript <json> -o src/api/generated/schema.d.ts`.
- **Prettier:** never run `prettier --write` on whole folders, only on the files a task changes.
  `ArchitectureDiagramPanel.tsx` isn't prettier-clean, so edit it by hand with minimal changes.
- **Real pricing data:** `../_DATA-PIPELINE` from the repo root, or `../../_DATA-PIPELINE` from
  `backend/`.

---

## Phase 1: Setup

**Purpose**: Confirm the starting point. There are no new dependencies.

- [ ] T001 Confirm the baseline on branch `020-provider-icons-connector-fixes`, and record the counts in the T040 notes:
  - backend `uv run pytest` and `uv run ruff check` pass
  - frontend `npm test`, `npm run build` and `npm run lint` pass

---

## Phase 2: Foundational

**Purpose**: There are no shared prerequisites. User Stories 1 and 2 touch different code, apart from the regenerated API types (`frontend/src/api/generated/schema.d.ts`, `frontend/src/api/client.ts`), which both stories change additively. If the stories are built in parallel, regenerate the types once after both backend schema changes are in (T005 and T022).

**Checkpoint**: Both stories can start.

---

## Phase 3: User Story 1 - Price Change reflects every pricing edit (Priority: P1) 🎯 MVP

**Goal**: Price Change and the "updated since last pricing" notice react to every edit that changes a price: vCPUs, memory, Azure OS and region. After a Duration switch, the previous contents are re-priced with their real provider, regions and options. Baselines stored by v0.0.2 are handled by the legacy rule, which on GCP and Azure shows "Not available: previous calculation from prior version is unreliable".

**Independent Test**: Quickstart sections A and B.

### Tests for User Story 1 (write first, and they must fail)

- [ ] T002 [P] [US1] Unit tests for `build_transient_architecture` in `backend/tests/unit/test_calculate_snapshot.py`:
  - The provider is taken from the request: a GCP request gives `architecture.provider == "gcp"`, and a missing provider gives `"aws"`.
  - Selections are grouped into one throwaway collection per distinct region.
  - A missing or null `region` falls back to `settings.aws_pricing_region`.
  - `provider_options` is copied onto each `SKUSelection`.
  - An empty list still raises `EmptySnapshotError`.
- [ ] T003 [P] [US1] Contract tests for `POST /api/v1/catalog/calculate-snapshot` in `backend/tests/contract/test_calculate.py`, against the fixture Parquet (`tests/fixtures/pricing_parquet`, which has aws, gcp and azure). Expected results:
  - A GCP request whose selection is a GCP machine core SKU with `gcp_machine` options returns the same `total_price` as calculating an architecture holding that selection.
  - Changing `vcpus` or `memory_gib` changes the total.
  - An Azure request with `azure_vm` `os: windows` returns the Windows meter's price, different from Linux.
  - An AWS request with `region` set to a non-us-east-1 fixture region returns that region's price.
  - An AWS request without `region` or `provider` returns exactly today's result (us-east-1).
  - Options whose `kind` doesn't match `provider` give a 422.
  - An empty `selections` gives a 400 `empty_snapshot`.
- [ ] T004 [P] [US1] Extend `frontend/tests/unit/priceChange.test.ts`:
  - **Version 2 baselines:**
    - Changing only `provider_options.vcpus`, only `memory_gib`, only `os`, or only `region` makes the contents count as changed (`direct`, or `duration_adjusted` when the Duration changed too).
    - Options with the same values in a different key order count as unchanged.
    - Editing a value and putting it back counts as unchanged.
  - **Legacy baseline** (no `version`):
    - Compared on the original five fields only.
    - A Duration change on provider `gcp` or `azure` gives the new outcome `unavailable`.
    - A Duration change on `aws` gives `duration_only` or `duration_adjusted`, as today.
    - Same Duration gives `direct` or `unchanged`, as today.
  - `pricedContentsEqual` compares `provider_options` for version 2 entries and ignores it for legacy entries.

### Implementation for User Story 1

- [ ] T005 [US1] In `backend/src/models/schemas.py`:
  - Add `provider: ProviderCode | None = None` to `CalculateSnapshotRequest`, using the existing provider literal or enum.
  - Add `region: str | None = None` and `provider_options: ProviderOptions | None = None` to `SnapshotSelection`.
  - Validate that each selection's options `kind` matches the request's provider (`gcp_machine` ↔ gcp, `azure_vm` ↔ azure), raising a 422 otherwise. Reuse the existing selection-create check if there is one.
- [ ] T006 [US1] Rework `build_transient_architecture` in `backend/src/services/price_calculation.py` to take the request's provider:
  - Set `Architecture(provider=...)`.
  - Build one `Collection` per distinct region, where a missing region means `settings.aws_pricing_region`.
  - Copy `provider_options` (as a plain dict, as stored on `SKUSelection`).
  - Update the docstring to drop the 010 "out of scope" note.
  - Pass `request.provider` from `calculate_snapshot` in `backend/src/api/calculate.py`.
  - T002 and T003 must pass.
- [ ] T007 [US1] Regenerate `frontend/src/api/generated/schema.d.ts` (see Shared notes), and update the `SnapshotSelection` and `calculateSnapshot(duration, selections, provider)` signatures in `frontend/src/api/client.ts`.
- [ ] T008 [US1] In `frontend/src/lib/priceChange.ts`:
  - Extend `PriceChangeSelection` with optional `region: string | null` and `provider_options: ProviderOptions | null`.
  - Add `version?: 2` to `PriorCalculation`.
  - Add a canonical options key (sorted-key JSON, or `null`).
  - Use the full key for version 2 baselines and the five-field key for legacy ones.
  - Add a `provider` parameter to `decideBaselineUpdate`, and the `unavailable` outcome for a legacy baseline + Duration change + `gcp`/`azure`.
  - Extend `PricedContentsEntry` with optional `provider_options`, and make `pricedContentsEqual` legacy-aware.
  - Update the doc comments. T004 must pass.
- [ ] T009 [P] [US1] Make the type guard in `frontend/src/lib/priorCalculation.ts` accept version 2 baselines (with `region` and `provider_options` per selection) and legacy ones (no `version`), and still drop unreadable values. Add or extend tests in `frontend/tests/unit/priceChange.test.ts`, or a new `frontend/tests/unit/priorCalculation.test.ts`, before changing the guard.
- [ ] T010 [P] [US1] Make the stored-result type guard in `frontend/src/lib/architecturePricingResults.ts` accept `pricedContents` entries with or without `provider_options`. Extend `frontend/tests/unit/architecturePricingResults.test.ts` first.
- [ ] T011 [US1] Wire it into `frontend/src/pages/WorkspacePage.tsx`:
  - `currentPriceChangeSelections` includes each selection's `region` (its collection's region, or a connector's "from" collection's) and `provider_options`.
  - `currentPricedContents` includes `provider_options`.
  - New baselines are stored with `version: 2`.
  - The Duration-switch path calls `api.calculateSnapshot(duration, prior.selections, provider)` with the regions and options.
  - On `unavailable`, skip the snapshot call, set Price Change to "not available" and store the new baseline.
- [ ] T012 [US1] In `frontend/src/components/workspace/PricingPanel.tsx`, show the "not available" state instead of a figure: the text "Not available: previous calculation from prior version is unreliable", in muted text, with the same placement as the Price Change line. Extend `frontend/tests/unit/PricingPanel.test.tsx` for this state.
- [ ] T013 [US1] Page-level tests in `frontend/tests/unit/WorkspacePage.pricing.test.tsx`, mocking `calculateSnapshot`:
  - On a GCP architecture, editing only vCPUs and recalculating shows Price Change = new − previous.
  - A Duration switch sends `provider: "gcp"`, regions and options to `calculateSnapshot`.
  - A legacy stored baseline plus a Duration switch on GCP shows the "Not available" note and makes no snapshot call.
  - The same on AWS still calls `calculateSnapshot`.
- [ ] T014 [US1] Run quickstart sections A and B against the real data (`_DATA-PIPELINE`), and record the results in `specs/020-provider-icons-connector-fixes/checklists/validation.md`. For step A5, include a hand check of the yearly comparison.

**Checkpoint**: User Story 1 is complete and can ship on its own as v0.0.3's Price Change fix.

---

## Phase 4: User Story 2 - GCP and Azure diagrams show their own icons (Priority: P2)

**Goal**:
- Each GCP and Azure service shows its own provider's icon.
- Disks, IP addresses, snapshots and load balancing inside large services show their more specific icon.
- Anything unmatched shows a 60 px fallback tile: a small provider logo with the service name, at most three lines, full name on hover.
- AWS is unchanged.

**Independent Test**: Quickstart section C.

### Tests for User Story 2 (write first, and they must fail)

- [ ] T015 [P] [US2] Unit tests for the generator in `backend/tests/unit/test_provider_icon_generator.py`, using small hand-made icon folders under `tmp_path`, with no real packages.
  - **Name normalization:**
    - `"Compute Engine"` ↔ `Compute-Engine.svg`
    - `"Virtual Machines"` ↔ `NNNNN-icon-service-Virtual-Machine.svg`
  - **No fuzzy matches:** `"MySQL by Bitnami"` doesn't match `Cloud-SQL`.
  - **Overrides win** over automatic matches.
  - **Duplicate Azure names:** the lowest-numbered file is picked, unless an override names one.
  - **GCP taxonomy-prefix overrides** and **Azure product-name pattern overrides**, ordered, first match wins.
  - **Deterministic output:** the same input gives byte-identical TS.
  - **Only referenced SVGs** are listed for copying.
  - **Coverage report:** the report lists categorized services (compute, storage, database or networking per `backend/src/db/seed/service_categories.json` rules) that have no icon.
- [ ] T016 [P] [US2] Unit tests for the shared resolver in `frontend/tests/unit/serviceIcons.test.ts`:
  - **AWS** delegates to `resolveAwsServiceIcon` and gives identical results.
  - **GCP:** a service-id match gives that icon, and a taxonomy-prefix override beats the service icon (Persistent Disk inside Compute Engine).
  - **Azure:** a product-name override (Managed Disks) beats the Virtual Machines icon.
  - **Fallback:** an unmatched GCP or Azure service gives `{ kind: "fallback", provider, name }`. The name comes from `service_name`, then the summary, then `service_code`.
  - **Never AWS:** neither GCP nor Azure ever returns an AWS icon URL.
- [ ] T017 [P] [US2] Contract test in `backend/tests/contract/` (the existing architecture-detail or SKU-selection contract test file): `SKUSelectionOut.service_name` is the provider's display name for a fixture GCP, Azure and AWS selection, and null when the SKU isn't in the snapshot.

### Implementation for User Story 2

- [ ] T018 [US2] Write `backend/scripts/generate_provider_service_icon_map.py` (research R5), following `generate_aws_service_icon_map.py`'s structure, which stays untouched.
  - **Arguments:** `--provider gcp|azure`, `--icons <package root>`, `--data-uri` (default `PRICING_DATA_URI`) and `--log-file`.
  - **Reading:** reads the newest snapshot through the manifests, the same as the AWS script.
  - **Matching:** exact matching on normalized names, plus checked-in `OVERRIDES` (service id → icon file) and `FAMILY_OVERRIDES` (service id → ordered `[match, icon]`) dicts in the script.
  - **Writes:**
    - `frontend/src/lib/{gcp,azure}ServiceIcons.generated.ts`, with exports `<P>_SERVICE_ICON_BY_ID` and `<P>_SERVICE_ICON_OVERRIDES` (data-model §5)
    - the referenced SVGs, copied unmodified into `frontend/src/assets/{gcp,azure}-icons/`
  - **Report:** prints matched, overridden, fallback, and categorized services without an icon.
  - T015 must pass.
- [ ] T019 [US2] Run the generator for GCP:
  ```
  cd backend && uv run python scripts/generate_provider_service_icon_map.py --provider gcp --icons ../../images-web/gcp_architecture_icons --data-uri file:///Users/Shared/agent-workspace/projects/cloud-pricing/_DATA-PIPELINE
  ```
  - Review the report.
  - Add `OVERRIDES` and `FAMILY_OVERRIDES` until "categorized services without an icon" is empty. Cover Compute Engine: Persistent Disk, snapshots, external IP addresses, load balancing, Cloud NAT. Also cover Cloud Storage, Cloud SQL, Spanner, Bigtable, Firestore, Memorystore, GKE, Cloud Run, Cloud DNS, Cloud CDN, Cloud VPN, Cloud Interconnect and Cloud Armor, where they appear in the data.
  - Re-run, and confirm a second run changes nothing.
  - Add `frontend/src/assets/gcp-icons/README.md`, naming the package and Google's usage terms (FR-014).
- [ ] T020 [US2] Run the generator for Azure (`--provider azure --icons ../../images-web/azure_architecture_icons`). Same review loop as T019, covering:
  - Virtual Machines, with a Managed Disks override to Disks, Public IP, Load Balancer and snapshots
  - Storage (Blob)
  - SQL Database
  - Cosmos DB
  - Redis
  - App Service
  - Functions
  - AKS
  - Virtual Network
  - VPN Gateway
  - Application Gateway
  - DNS
  - Front Door / CDN
  - Bandwidth

  Add `frontend/src/assets/azure-icons/README.md`, naming the package and Microsoft's terms.
- [ ] T021 [US2] Write `frontend/src/lib/serviceIcons.ts`, exporting `resolveServiceIcon(provider, selection)`. It returns either today's `ResolvedServiceIcon`, or `{ kind: "fallback"; provider: "gcp" | "azure"; name: string; logoUrl: string }`.
  - **AWS:** delegates to `resolveAwsServiceIcon`, unchanged.
  - **GCP and Azure:** resolve from the generated modules, loading SVG URLs the same way as `awsServiceIcons.ts` (`import.meta.glob` on `../assets/{gcp,azure}-icons/*.svg`).
  - **Logos:** taken from `frontend/src/assets/providers/{gcp,azure}_icon.png`.
  - T016 must pass.
- [ ] T022 [US2] Add `service_name: str | None = None` to `SKUSelectionOut` in `backend/src/models/schemas.py`. Set it in `backend/src/services/architecture_service.py`, next to `out.attributes` and `out.product_family`, from the resolved catalog item. Regenerate the API types (see Shared notes; combine with T007 if both are pending). T017 must pass.
- [ ] T023 [US2] In `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`, make minimal hand edits (no prettier on the whole file):
  - The service icon button takes the architecture's provider and calls `resolveServiceIcon` instead of `resolveAwsServiceIcon`.
  - When the result is a fallback, it renders the fallback tile inside the same 60 × 60 px button:
    - a 20 px logo on a small white rounded badge
    - the name under it, in `text-2xs` with the theme's foreground token, `line-clamp-3` and `break-words`
  - The tooltip and accessible name are unchanged.
  - Thread the provider through from the panel's props, for both the main diagram and the pop-out (`PopoutCanvasDialog`), and through `WorkspacePage.tsx`.
- [ ] T024 [US2] Extend `frontend/tests/unit/ServiceIconList.test.tsx`, or add `frontend/tests/unit/serviceIconTile.test.tsx`:
  - **GCP:** a selection with a mapped service renders that icon.
  - **GCP fallback:** an unmatched selection renders the logo and its name. A long name is clamped, and the full name is still the accessible name.
  - **AWS:** a selection renders exactly as before.
  - **Positions:** icon positions are unchanged for all three (FR-013).
- [ ] T025 [US2] Run quickstart section C against the real data, in light and dark themes, and record the results in `specs/020-provider-icons-connector-fixes/checklists/validation.md`. This covers:
  - the specific icons
  - the fallback tiles and several fallbacks on one diagram
  - AWS unchanged
  - v0.0.2 layouts kept
  - the pop-out
  - the generator re-run giving no changes

**Checkpoint**: User Story 2 is complete and can ship on its own.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T026 [P] Update `README.md`: GCP and Azure icons, and the Price Change fix.
- [ ] T027 [P] Write `specs/020-provider-icons-connector-fixes/release-notes.md` for v0.0.3. It covers:
  - the Price Change fix, including the one AWS change after a Duration switch with boxes outside us-east-1, and the "Not available" note for old GCP and Azure baselines
  - the GCP and Azure icons and the fallback tiles
  - that connectors are unchanged and their redesign follows the UI overhaul
- [ ] T028 Run quickstart section D (regression), then the full checks:
  - backend: `uv run pytest` and `uv run ruff check`
  - frontend: `npm test`, `npm run build`, `npm run lint` and the API-type check
  - the account-ID grep

  Record the results in `checklists/validation.md`, and compare the counts with T001's.

---

## Dependencies & Execution Order

- **Phase 1** comes first. **Phase 2** is empty.
- **US1 (Phase 3) and US2 (Phase 4) are independent.** They meet only at the regenerated API types (T007 and T022) and at `WorkspacePage.tsx` (T011 and T023).
- **Within US1:**
  - T002, T003 and T004 come first.
  - T005 → T006 → T007.
  - T008 depends on T004 and T007.
  - T009 and T010 can run in parallel after T008.
  - T011 depends on T008 to T010. T012 depends on T011, and T013 on T011 and T012. T014 comes last.
- **Within US2:**
  - T015, T016 and T017 come first.
  - T018 → T019 and T020.
  - T021 depends on T016, T019 and T020.
  - T022 depends on T017.
  - T023 depends on T021 and T022. T024 depends on T023, and T025 comes last.
- **Polish:** after the stories being shipped are done.

## Parallel Examples

```text
# US1 tests together:
T002 backend/tests/unit/test_calculate_snapshot.py
T003 backend/tests/contract/test_calculate.py
T004 frontend/tests/unit/priceChange.test.ts

# US2 tests together:
T015 backend/tests/unit/test_provider_icon_generator.py
T016 frontend/tests/unit/serviceIcons.test.ts
T017 backend/tests/contract/<selection contract test>

# After T018, both generator runs can proceed independently:
T019 (gcp)  T020 (azure)

# After T008:
T009 frontend/src/lib/priorCalculation.ts
T010 frontend/src/lib/architecturePricingResults.ts
```

## Implementation Strategy

- **MVP:** User Story 1 alone (T001 to T014). It fixes a wrong number and is the smallest change.
- **Then:** User Story 2 (T015 to T025). Most of its time goes on reviewing the generator's report and writing overrides (T019, T020).
- **Release:** both stories plus polish give v0.0.3. Either story can also ship alone, if the other slips.
- **Commits:** at the end of each story's checkpoint, only when the user runs `/speckit-git-commit`.
  - Stage with `git add -A -- . ':!specs/018-app-cloud-deployment/acceptance.md'`.
  - Use a conventional message ending with the Co-Authored-By line.
