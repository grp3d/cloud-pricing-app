# Feature Specification: Agent Pricing Questions and Comparisons (Read-Only)

**Feature Branch**: `024-agent-pricing-questions`

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: "../speckit-inputs/agent-02-pricing-questions.md" (agent feature 2
of 4; builds on 023, the agent foundation; follows constitution 1.2.0, Principles I, III, V, VII
and VIII)

## Overview

Users ask the agent price questions in plain language: "How much cheaper is object storage on
Azure than GCP?", "What would this architecture cost on Azure?", "What's the on-demand price of
an m5.large in eu-west-1?" The agent asks only the follow-up questions it needs, states its
assumptions, runs the comparison through the pricing engine, and answers with the figures, the
difference and the basis of comparison. Nothing in this feature changes a saved architecture.

**Why:** comparing prices across providers by hand means matching services, tiers, units and
durations. The value is a correct, clearly stated comparison without that effort, with honesty
about what can't be compared.

**Comparison basis.** Every comparison states its basis: for each provider, the category, the
product matched and how closely it matches, the region, the usage, the duration, the pricing
term, the currency (USD), and that provider's pricing snapshot date. When products aren't truly
equivalent, the answer says how they differ.

**Where results appear.** The agent's explanation stays in the conversation; each comparison's
table appears in a Results pane beside the conversation, inside the Agent tab, with a download
button. A short card in the conversation links each answer to its result.

**Builds on 023.** The Agent tab, sessions, limits, the activity log, the evaluation set and the
rule that every figure comes from the pricing engine (the model refers to figures; the app fills
them in) all carry over unchanged.

## Clarifications

### Session 2026-11-13

- Q: For an architecture comparison, how should the agent collect the matching product for each
  service on the other provider? → A: One app operation returns, for every service at once, the
  top same-category candidates on the target provider; the agent picks one per service (or no
  equivalent) with quality and differences; one more operation prices all picks together.
- Q: In one architecture comparison, can the user compare against both other providers at
  once, or only one at a time? → A: Both at once; the table shows the current provider plus one
  or two targets, each with its match, quality, figure and difference from the current provider.
- Q: How should match quality be decided for each matched product? → A: The app sets the
  highest quality the attributes allow by fixed rules; the agent may lower it with a stated
  reason, never raise it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare a service category across providers (Priority: P1)

A user asks how two or more providers compare for something like object storage or a
general-purpose virtual machine. They get each provider's figure, the difference in amount and
in percentage, and the basis.

**Why this priority**: it's the core of the feature: a correct, stated comparison that would
otherwise take several catalog searches and calculations per provider.

**Independent Test**: for a benchmark set of category questions, every figure in the answer
equals what the pricing engine returns for the stated basis, and every answer states the basis
and snapshot dates.

**Acceptance Scenarios**:

1. **Given** a question that leaves out details the price depends on (for example storage type,
   access tier, redundancy, region or amount), **When** the user asks it, **Then** the agent
   either asks a short question (at most three questions in all) or states a default and
   answers.
2. **Given** the agent has asked for details, **When** the user replies "use defaults" (or
   similar), **Then** the agent states every default it chose, including any region it guessed,
   and answers.
3. **Given** an answer, **Then** it includes each provider's figure, the difference in amount
   and in percentage, the basis and each provider's snapshot date.
4. **Given** an answer, **When** the user asks a follow-up that changes one thing ("and for
   10 TB?", "what about 3-year reserved?"), **Then** the agent reuses the rest of the basis and
   says what changed.

---

### User Story 2 - Compare the open architecture across providers (Priority: P1)

The user asks "what would this architecture cost on Azure?", "what would my storage cost on
GCP?" or "what would this cost on the other two clouds?". The agent takes the open architecture's services and usage as the inputs, matches each
service on the target provider for this comparison only, and shows the per-service and total
figures and differences. Nothing is created or saved; building the equivalent architecture is
agent-04.

**Why this priority**: it answers the question users actually have about their own design,
using the work they've already done.

**Independent Test**: for each standard architecture compared with another provider, every
matched service's figure equals the pricing engine's for the stated match and usage, unmatched
services are listed, and a total that leaves any out is labelled partial.

**Acceptance Scenarios**:

1. **Given** an open architecture, **When** the user asks what it would cost on another
   provider, **Then** the answer lists each service with its match on that provider, how
   closely it matches, both figures and the difference, then both totals and the difference.
2. **Given** some services have no match, **Then** they're listed as unmatched, and the total
   is labelled as partial (covering only the matched services) on both sides.
3. **Given** the user asks about part of the architecture ("my storage"), **Then** only the
   services in that category are compared.
4. **Given** the comparison is shown, **Then** the open architecture is unchanged and nothing
   new is saved.
5. **Given** the user asks for both other providers at once, **Then** one result shows the
   current provider and both targets side by side, each target with its match, quality, figure
   and difference from the current provider, and a total per provider (partial where needed).

---

### User Story 3 - Be honest about products that aren't equivalent (Priority: P1)

When the providers' products differ (a different tier, size limit, redundancy model or billing
unit), the agent names the closest match, states the differences, and doesn't present the
figures as like for like.

**Why this priority**: a confident comparison of unlike products is the most damaging mistake a
comparison tool can make.

**Independent Test**: for benchmark questions whose products differ, every answer names the
match quality and at least one concrete difference.

**Acceptance Scenarios**:

1. **Given** a tier that exists on one provider and has no counterpart on another, **When** it
   is compared, **Then** the agent says there's no direct counterpart, shows the closest match
   and lists the differences.
2. **Given** products billed in different units (for example per hour versus per second, or per
   GB versus per GiB), **Then** the agent states the units and the usage it converted, and the
   conversion is the app's, not the model's.

---

### User Story 4 - Missing data is never estimated (Priority: P1)

If pricing for a provider, region, product or pricing term is unavailable, the agent says so
and doesn't fill the gap.

**Why this priority**: required by Principle I; one invented price destroys trust in all the
others.

**Independent Test**: with pricing removed for one provider in a region, the comparison shows
the other providers and says that provider can't be priced there.

**Acceptance Scenarios**:

1. **Given** no pricing for one provider in the chosen region, **When** the comparison runs,
   **Then** the answer shows the other providers and says that provider can't be priced there,
   without a figure, difference or percentage for it.
2. **Given** a pricing term one provider doesn't offer for that product, **Then** the agent
   says so and offers the terms it does offer.
3. **Given** a provider's pricing data is unavailable or out of date in the app, **Then** the
   answer says so and shows that provider's snapshot date.

---

### User Story 5 - Look up a specific price (Priority: P2)

A user asks for a single price (a named product in a region, with a pricing term) and gets the
figure with its basis.

**Why this priority**: useful and simple, but the comparisons above carry the feature.

**Independent Test**: for a benchmark set of single-price questions, every figure equals the
pricing engine's for the stated basis.

**Acceptance Scenarios**:

1. **Given** a named product, region and term, **When** the user asks its price, **Then** the
   answer gives the figure for the stated usage and duration, with the basis and snapshot date.
2. **Given** a product name that matches several catalog entries, **Then** the agent asks
   which one, or states which it chose and why.

---

### User Story 6 - See and save comparison results (Priority: P1)

A comparison's table appears in a Results pane on the right of the Agent tab, beside the
conversation, separated by a bar the user can drag. The user can step through this session's
results, reopen one from its card in the conversation, and download the one shown as a CSV file.

**Why this priority**: a comparison of an architecture can run to 10–20 rows; it's readable
only as a table, and users want to keep it outside the app.

**Independent Test**: after two comparisons in a session, the Results pane shows the second,
steps back to the first, and the downloaded CSV of each contains exactly the rows and figures
shown, with the basis, and empty marked cells for unavailable prices.

**Acceptance Scenarios**:

1. **Given** no result yet in the session, **Then** the Agent tab shows only the conversation.
   **When** the first comparison finishes, **Then** the Results pane opens beside the
   conversation and shows its table.
2. **Given** a comparison answer, **Then** the conversation shows the agent's explanation and a
   card naming the comparison (for example "AWS vs Azure · 14 rows · total +12%"); **When** the
   user selects the card, **Then** the Results pane opens (if closed) and shows that result.
3. **Given** several results in a session, **When** the user steps back and forward in the
   Results pane, **Then** it shows each result in turn with its position ("2 of 3").
4. **Given** the Results pane is open, **When** the user closes it, **Then** only the
   conversation shows, and the results stay available from their cards.
5. **Given** a result is shown, **When** the user selects Download, **Then** a CSV file is
   saved with the basis (providers, regions, usage, duration, pricing terms, currency, snapshot
   dates) followed by exactly the rows and totals shown; unavailable prices are left empty and
   marked unavailable, never written as 0.
6. **Given** the user drags the bar between the conversation and the Results pane, **Then** the
   split changes and is kept for that user the next time the Agent tab opens.
7. **Given** the Agent tab is too narrow for two columns, **Then** the Results pane is shown
   below the conversation instead of beside it.
8. **Given** a session with results, **When** the user reopens that session later (for
   example after a reload), **Then** its cards are there and the Results pane is open on the
   session's latest result.

---

### Edge Cases

- **A region that doesn't exist on a provider**: the agent says so and offers that provider's
  regions with the closest names; nothing is priced in an invented region.
- **No region given**: the agent proposes a best guess per provider from the region names, says
  it's a guess, and the user can change it (there's no curated region matching).
- **Different billing units or minimum commitments**: stated in the basis; the usage
  conversion is done by the app.
- **A question spanning many categories** ("compare everything"): the agent asks which
  categories, or compares the open architecture category by category.
- **No real comparison** ("which cloud is best?"): the agent says it doesn't recommend a
  provider, and offers a price comparison for a specific category or the open architecture.
- **A pricing term one provider doesn't offer**: stated; that provider is shown on its nearest
  available term only if the user agrees, and labelled as such.
- **Stale data on one provider**: the snapshot date is shown; the other providers aren't
  affected (Principle I).
- **Several regions on one provider in one question**: compared as asked, with one column
  group per provider and region in the same result.
- **The open architecture is on the provider being compared to**: the agent says it's already
  on that provider and offers the current total instead.
- **A follow-up after the open architecture changed**: the comparison uses the architecture as
  it is now, and says so.
- **The user asks the agent to build or save the comparison as an architecture**: the agent
  says it can't yet (agent-04) and points to what it can do.
- **A single-price lookup**: answered in the conversation only; it doesn't open the Results
  pane.
- **A comparison where nothing could be priced**: no result table is made; the answer says
  what couldn't be priced and why.
- **A new agent session**: starts with no results and the Results pane hidden.
- **A follow-up that changes the basis**: produces a new result; earlier results are kept
  unchanged, so they can be compared side by side by stepping between them.
- **A product or service name containing commas, quotes or line breaks**: the CSV stays valid
  and opens in common spreadsheet tools with the same rows and columns.

## Requirements *(mandatory)*

### Functional Requirements

**Figures and basis**

- **FR-001**: Every figure (price, total, difference, percentage) MUST come from the app's
  pricing operations, in USD to 2 decimal places; differences and percentages MUST be computed
  by the app from the engine's unrounded values. The model refers to figures; the app fills
  them in (as in 023).
- **FR-002**: Every comparison MUST state its basis (for each provider: category, product
  matched, match quality, region, usage, duration, pricing term, USD) and each provider's
  snapshot date.
- **FR-003**: Durations MUST be the app's (1 day, 1 month = 31 days, 1 year = 365 days); "per
  month" means the 1-month duration.
- **FR-004**: Pricing terms MUST be those the app supports for each provider (AWS: on demand;
  reserved 1 or 3 years with no, partial or all upfront. GCP: on demand; committed use 1 or 3
  years. Azure: on demand; savings plan 1 or 3 years; reservation 1 or 3 years). When the user
  doesn't name one, the default MUST be on demand, stated as an assumption.

**Asking and assuming**

- **FR-005**: The agent MUST ask at most three clarifying questions before answering, and MUST
  offer to proceed with stated defaults.
- **FR-006**: Every default and assumption the agent used MUST be stated in the answer.
- **FR-007**: A region the agent guessed MUST be stated as a guess, and the user MUST be able to
  change it in a follow-up.
- **FR-008**: Follow-up questions MUST reuse the prior basis unless the user changes it, and the
  answer MUST say what changed.

**Matching and honesty**

- **FR-009**: Matching a product across providers MUST use the app's categories and pricing
  catalog. Until agent-04's reviewed mapping data exists, the agent chooses the match by
  searching the other provider's catalog within the same category; every match MUST be shown
  with its quality (exact, close, partial or no equivalent) and its differences, and the user
  can correct a match in a follow-up. Prices still come only from the engine; agent-04's
  reviewed mappings replace the agent's choice once they exist.
- **FR-009a**: For an open-architecture comparison, one operation MUST return, for every
  service at once, the top few candidate products in the same category on the target provider;
  the agent picks one per service (or no equivalent), and one further operation MUST price all
  the picks together. The candidates MUST be the same for the same architecture and catalog, and
  a comparison of any architecture MUST fit within one message's round limit from 023. One
  comparison MAY target one or both other providers; both operations MUST accept several
  target providers at once.
- **FR-009b**: Match quality MUST be set by the app from the products' catalog attributes,
  using fixed rules: **exact** (same function, billing unit and key specifications such as
  vCPU, memory, tier and redundancy), **close** (same function with small differences in
  specifications or units), **partial** (covers only part of the function, or a different
  billing model), **no equivalent** (no usable product). The app's label is the highest the
  match may carry; the agent MAY lower it, and MUST then state why, but MUST NOT raise it. The
  differences the app found MUST be shown with the match.
- **FR-010**: When products aren't equivalent, the answer MUST say so and describe the
  differences; figures for unlike products MUST NOT be presented as like for like.
- **FR-011**: The agent MUST NOT estimate, infer or carry over a missing price. A provider,
  region, product or term that can't be priced MUST be shown as unavailable, with no figure,
  difference or percentage for it.
- **FR-012**: For an open-architecture comparison, unmatched or unpriceable services MUST be
  listed, and any total that leaves them out MUST be labelled partial on both sides.

**Presentation**

- **FR-013**: A comparison MUST be shown as a table the app draws from the comparison's result
  (the basis; per provider, and per service for an architecture: the product matched, match
  quality, figure or "unavailable", difference and percentage; totals, labelled partial where
  something was left out), in a Results pane in the Agent tab. The agent's explanation MUST
  stay in the conversation, and the table's figures MUST NOT pass through the model. A
  single-price lookup is answered in the conversation and makes no table.
- **FR-018**: The Results pane MUST be hidden until the session's first result, open
  automatically when a result arrives (and, when a session with results is reopened, open on
  its latest result), sit to the right of the conversation with a draggable
  divider, and be closable. Below a minimum Agent tab width it MUST stack below the
  conversation instead. The divider position MUST be saved with the user's workspace
  preferences.
- **FR-019**: Each comparison answer MUST include a card in the conversation that names its
  result and a one-line summary; selecting it MUST show that result. The Results pane MUST let
  the user step through the session's results in order, showing the position ("2 of 3").
- **FR-020**: The Results pane MUST offer Download CSV for the result shown, saving a CSV file to
  the user's device that contains the basis and snapshot dates followed by exactly the rows and
  totals shown. Unavailable prices MUST be empty and marked unavailable, never 0; a partial
  total MUST be labelled partial. Text cells MUST be written so that a spreadsheet tool can't
  treat them as formulas (names come from users and imported architectures). CSV is the only
  download format in this feature.
- **FR-021**: Results MUST be saved with the agent session, so reopening a session shows its
  results and cards as they were; results MUST be visible only to the session's owner, like
  the session itself.

**Read-only and transparency**

- **FR-014**: This feature MUST NOT change or create a saved architecture.
- **FR-015**: Every comparison and lookup MUST appear in the activity log with its inputs (the
  basis), its outcome, and the snapshot behind each figure (as in 023).
- **FR-016**: The agent MUST NOT recommend which provider to choose; it answers with prices and
  differences.

**Evaluation**

- **FR-017**: The golden conversations below MUST be added to the evaluation set, with fixed
  checks only (figures equal the engine's for the stated basis; required phrases; operations
  run), runnable with the scripted model by default and against configured models on request.

### Golden Conversations (seed for the evaluation set)

Expected figures are always computed by the pricing engine for the stated basis.

- **GC-1**: "How much cheaper is storage on Azure than GCP?" The agent asks about or states:
  storage type (object, block, file), access tier, redundancy, the region on each provider and
  the amount. It answers with each provider's monthly figure, the difference and the basis.
- **GC-2**: The user answers "whatever, use defaults." The agent states the defaults, including
  its region guess, and answers.
- **GC-3**: A tier exists on one provider and has no counterpart on another. The agent says so
  and shows the closest match with the differences.
- **GC-4**: Pricing is missing for one provider in the chosen region. The agent says it can't
  price that provider and shows the others.
- **GC-5**: A follow-up, "and for 10 TB?" The agent reuses the previous basis and changes only
  the amount.
- **GC-6**: "What would this architecture cost on GCP?" Per-service and total comparison, with
  unmatched services listed and the total labelled partial.
- **GC-7**: "Which cloud is best?" The agent doesn't recommend a provider and offers a specific
  comparison instead.
- **GC-8**: "What's the on-demand price of an m5.large in eu-west-1 per month?" The figure
  equals the engine's, with the basis.

### Key Entities *(include if feature involves data)*

- **Comparison Question**: what the user asked, the providers and category involved, and
  whether it is about a category, the open architecture or a single price.
- **Comparison Basis**: for each provider, the category, product matched, match quality,
  region (and whether it was guessed), usage, duration, pricing term and currency. Reused by
  follow-ups until changed.
- **Match**: a source product, the chosen target product, the app's quality label, the label
  shown (equal or lower, with the agent's reason if lower) and the differences found.
- **Comparison Result**: per provider (and per service, for an architecture), the figure or
  "unavailable", the snapshot date, and the differences in amount and percentage; totals
  marked partial where something was left out.
- **Assumption**: a default the agent chose (a term, a tier, a region guess, a usage amount),
  shown with the answer.
- **Result**: a comparison result saved with its session and the message that produced it,
  with a short title and summary for its card; it can be shown in the Results pane and
  downloaded.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of figures in benchmark answers match the pricing engine for the stated
  basis, to the cent.
- **SC-002**: 100% of comparison answers state a basis and each provider's snapshot date.
- **SC-003**: For the benchmark set, at least 90% of answers are reached with three or fewer
  clarifying questions.
- **SC-004**: 100% of benchmark cases with missing pricing show "unavailable" for that provider
  and no figure, difference or percentage for it.
- **SC-005**: No benchmark answer recommends a provider, and none presents a non-equivalent
  match without saying so.
- **SC-006**: All golden conversations pass with the scripted model in every test run, and on
  two configured models in the opt-in live run: one local (llama3.1 through Ollama) and one
  hosted (Claude Sonnet 5.5).
- **SC-007**: After any number of comparisons, every saved architecture is unchanged.
- **SC-008**: For every benchmark comparison, the downloaded CSV contains the same rows,
  figures and totals as the Results pane, opens in common spreadsheet tools without errors,
  and has no figure for any unavailable price.

## Assumptions

- Pricing data for all three providers is in the app, with the four categories (compute,
  storage, database, networking) and the pricing terms listed in FR-004.
- Agent-04's reviewed mapping data doesn't exist yet; 022 produced match reports for the four
  standard architectures, not reusable mapping data.
- Usage defaults (for example an amount of storage, or a machine running all day) are the app's
  own defaults where it has them, and are always stated.
- Region guesses use only the providers' region names and locations as the app lists them;
  there's no curated region matching (a possible later addition).
- The explanation is written in the conversation and the table in the Agent tab's Results
  pane; there's no separate comparison page. The Results pane is meant to also hold later
  agents' structured output (agent-03 and agent-04), but this feature only puts comparisons
  in it.
- The CSV opens in common spreadsheet tools; other download formats (for example Excel) can be
  added later.
- The limits, preview, cost cap, timeout and model settings from 023 apply unchanged; a
  comparison can take several operations within one message (023's maximum rounds per message
  apply).

## Out of Scope

- Changing, creating or importing architectures (agent-03), and building the equivalent
  architecture on another provider (agent-04).
- Curated region matching, and reviewed cross-provider mapping data (agent-04).
- Recommending which provider to choose.
- Currencies other than USD; durations other than the app's three.
- Download formats other than CSV; downloading several results at once; sharing results with
  other users.
