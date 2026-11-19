# Feature Specification: Agent Cross-Cloud Architecture Translation

**Feature Branch**: `026-agent-cross-cloud-translation`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "../speckit-inputs/agent-04-cross-cloud-translation.md" (agent
feature 4 of 4; builds on 023, the agent foundation, 024, pricing questions and comparisons, and
025, agent-built architectures; seeded by 022, the GCP and Azure standard architectures; follows
constitution 1.2.0, Principles I, III, V, VII and VIII)

## Overview

A user asks the agent, for example, "Build the equivalent of my AWS architecture 'Prod Web' in
Azure, in East US." The agent proposes a **new architecture on the target provider**: every
service matched to its equivalent there, with the original's grouping, nesting and connections
kept. The proposal shows a **mapping table** (each source service, what it was matched to, how
good the match is, where the match came from, and the assumptions made) and the cost of the
original and the translation for the same duration, with the difference and its main drivers,
all from the pricing engine. Accepting creates the new architecture, private to the user, as 025
does; the original is never changed.

**Why:** moving or comparing across clouds means finding the equivalent of every service and
re-pricing everything. It is the most valuable thing the agent can do and the riskiest: a wrong
match gives a confident but misleading number. Trust depends on showing every match, how good it
is, and what couldn't be matched.

**Service mappings are the app's data, not the model's knowledge.** The app keeps mappings from
one provider's kinds of product to another's. The matches 022 made for the four AWS standard
architectures are the seed mappings. Other matches are found automatically from each product's
category and attributes in the catalog and rated by 024's match quality (exact, close, partial or
no equivalent). Exact and close matches are used straight away. A partial match is never used
unless **the user chooses it** in the conversation, after seeing its differences; the choice
applies to that proposal only and is disclosed wherever the cost is given. There is no Admin
review: nobody waits on anyone else.

**Builds on 023–025.** The Agent tab, sessions, limits, the activity log, the evaluation set, the
Results pane, the rule that every figure comes from the pricing engine, the answering rules (at
most three questions before offering defaults, stating assumptions, saying when a region is a
guess, never naming a product the catalog didn't return), proposals with Accept and Reject, and
Undo and Redo all carry over unchanged.

**First release:** AWS → GCP and AWS → Azure. The other four directions, and several targets in
one request, come later.

## Clarifications

### Session 2026-11-19

- Q: Which automatic matches can be used without review? → A: Exact and close matches; where
  several qualify, the user's choice or the stated default (best quality, then lowest price).
- Q: Is a mapping per kind of product in every region, per pair of regions, or per price entry?
  → A: Per kind of product (instance type, database class, storage class), in every region;
  prices come from the chosen target region, and a matched product not sold there is flagged and
  left out.
- Q: How is a doubtful (partial) match settled: by an Admin review queue, or otherwise? → A: The
  user decides in the conversation, for that proposal only; there is no Admin review queue and
  the shared mapping data doesn't change.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Translate an architecture to another provider (Priority: P1)

A user names an architecture (open or not, their own or a public one) and a target provider. The
agent asks only for what the mapping data can't settle: the target region for each source region
(offering a guess), the pricing term, a choice where a service has several valid equivalents,
and whether to use a partial match. It then proposes a new architecture on the target provider
that keeps the original's collections, nesting and connections.

**Why this priority**: this is the feature. Without it there is nothing to review or accept.

**Independent Test**: for each of the four AWS standard architectures, translated to GCP and to
Azure, every source service in the proposal is either matched (seeded, automatic, or chosen by
the user) or flagged as having no equivalent, and the proposal has the same collections, nesting
and connections as the original.

**Acceptance Scenarios**:

1. **Given** a source architecture and a target provider, **When** the user asks for a
   translation, **Then** the agent asks only for details the mapping data can't settle (target
   regions, pricing term, a choice among several valid equivalents, whether to use a partial
   match), at most three questions, and offers its defaults.
2. **Given** the user named no target region, **When** the agent asks, **Then** it offers a guess
   for each source region, says it is a guess, and asks the user to confirm.
3. **Given** a service with several valid equivalents, **When** the agent proposes, **Then** it
   presents the choices with their differences and the user picks one, or accepts a stated
   default.
4. **Given** the proposal, **When** it is shown, **Then** it keeps the original's collections,
   their nesting and their connections, each collection in its chosen target region.
5. **Given** an architecture the user doesn't own (a public one), **When** they ask for a
   translation, **Then** the agent translates it the same way; the result is the user's own.

---

### User Story 2 - Review the mapping and the cost difference (Priority: P1)

The proposal, in the Results pane, shows a mapping table with a row for each source service: the
source service, the matched service, the match quality, where the match came from ("seeded",
"automatic" or "chosen by you"), and the assumptions. It shows the original's total and the
translation's total for the same duration, the difference in amount and percentage, and the main
drivers of the difference, all from the pricing engine. A card under the answer names the
translation and its difference.

**Why this priority**: the user can only trust and accept a translation they can check, match by
match.

**Independent Test**: for each translation in the test set, every total, difference and
percentage equals the pricing engine's to the cent, and the table has exactly one row per source
service.

**Acceptance Scenarios**:

1. **Given** a translation proposal, **When** it is shown, **Then** each source service has one
   row with its match, match quality, where the match came from, and assumptions, and each match
   that isn't exact lists its differences.
2. **Given** a translation proposal, **When** it is shown, **Then** both totals are for the same
   duration and snapshot dates are given for both providers.

---

### User Story 3 - Doubtful and missing matches are never guessed (Priority: P1)

A service with no candidate is flagged in the mapping table, left out of the translation and its
total, and the total is labelled partial. A service whose only candidates are partial matches is
left out the same way unless the user, shown the candidates and their differences, chooses one.
The agent never substitutes a doubtful match on its own.

**Why this priority**: a guessed match is the main way this feature could mislead.

**Independent Test**: for translations that include services with no candidate or only partial
candidates, those services are flagged and absent from the new architecture and its total, and
the total is labelled partial, unless the user chose a partial match, in which case the row says
"chosen by you" and every cost answer names it.

**Acceptance Scenarios**:

1. **Given** a source service with no candidate, **When** the agent proposes, **Then** the service
   is flagged with the reason, left out, and the total is labelled partial.
2. **Given** a source service with only partial candidates, **When** the agent proposes, **Then**
   it shows the candidates with their differences and asks whether to use one; by default the
   service is left out and the total is labelled partial.
3. **Given** the user chooses a partial match, **When** the proposal is shown, **Then** the row is
   marked "partial, chosen by you" with its differences, and the mapping data is unchanged.
4. **Given** a source service that is already unpriceable in the original, **When** it is
   translated, **Then** it is flagged as unpriceable on both sides, not reported as a saving.

---

### User Story 4 - Accept, reject, undo (Priority: P1)

Accepting creates the translation as a new architecture, private and owned by the user, and opens
it. Rejecting creates nothing. Undo removes the created architecture and Redo creates it again,
as 025 does for a new architecture. The original is untouched in every case.

**Why this priority**: a translation that can't be safely accepted or taken back can't be used.

**Independent Test**: accept, undo, redo and reject translations of each standard architecture;
the original's saved state is identical before and after every step, and the created
architecture exists only between accept (or redo) and undo.

**Acceptance Scenarios**:

1. **Given** a translation proposal, **When** the user rejects it, **Then** no architecture is
   created and the original is unchanged.
2. **Given** a translation proposal, **When** the user accepts it, **Then** a new private
   architecture owned by the user is created on the target provider with exactly the proposed
   contents, and it opens.
3. **Given** an accepted translation, **When** the user selects Undo, **Then** the new architecture
   is removed; Redo creates it again.

---

### User Story 5 - Adjust the translation in conversation (Priority: P2)

The user swaps a matched service for another valid option ("use the cheaper database tier"), or
for a partial candidate they now want to use, and the proposal and its cost update. This changes
only the proposal, not the mapping data.

**Why this priority**: the default match is a starting point; the user often has a preference.

**Independent Test**: refine a pending translation; the proposal is replaced, the swapped row
shows the new match, the totals equal the engine's, and the mapping data is unchanged.

**Acceptance Scenarios**:

1. **Given** a pending translation, **When** the user asks for another valid option for a
   service, **Then** the agent revises the proposal, says what changed, and the cost updates.
2. **Given** a requested option that isn't a candidate (another category, or not in the catalog
   in that region), **When** the user asks, **Then** the agent says so and the proposal is
   unchanged.

---

### User Story 6 - Answer "which is cheaper?" honestly (Priority: P2)

Asked which provider is cheaper, the agent answers from the two totals and states the caveats
that apply: services left out or unmatched, partial totals, matches that aren't exact (naming any
partial match the user chose), and differing assumptions (terms, regions, sizing). It doesn't
declare a winner without them.

**Why this priority**: a bare winner from a partial comparison is exactly the misleading answer
the feature must avoid.

**Independent Test**: for translations with and without left-out services, the answer gives both
totals and, whenever the translation is partial or has matches that aren't exact, names them.

**Acceptance Scenarios**:

1. **Given** a complete translation with only exact matches, **When** the user asks which is
   cheaper, **Then** the agent answers from the totals and the difference.
2. **Given** a partial translation, **When** the user asks which is cheaper, **Then** the agent
   says the comparison is partial, names what was left out, and doesn't present the difference as
   the whole saving or cost.

---

### Golden conversations (evaluation set)

Scripted for the automated tests and run live on the evaluation model (SC-005):

- **GC-1:** "Build the equivalent of 'Prod Web' in Azure." The agent asks for the target regions
  (offering a guess) and the pricing term, then presents the mapping table and the cost
  difference.
- **GC-2:** A service has three valid equivalents. The agent presents them with their differences,
  and the user chooses.
- **GC-3:** A service has no equivalent. It's flagged, left out, and the total is partial.
- **GC-4:** The source uses reserved pricing. The agent states which term it assumes on the target
  and why.
- **GC-5:** "So which is cheaper?" The agent answers with the totals and the caveats.
- **GC-6:** The user rejects the translation. No architecture is created, and the original is
  unchanged.
- **GC-7:** A service has only a partial candidate. The agent shows it with its differences; the
  user chooses to use it; the row says "partial, chosen by you", and the cost answer names it.

### Edge Cases

- **A target region doesn't exist on the provider, or has no pricing data**: the agent says so and
  offers the nearest region that does, as a guess to confirm.
- **The matched product isn't sold in the chosen target region**: the service is flagged and left
  out, and the total is labelled partial.
- **The source spans several regions**: each source region gets its own target region; the user
  confirms them all at once.
- **Services whose behaviour differs materially** (limits, availability, consistency): the match
  is at most "partial" by 024's rules, so it is used only if the user chooses it, and the
  difference is listed.
- **Data transfer and connections**: a connector's data-transfer service is translated like any
  other service; where the target prices it differently (or not at all), the row says so and the
  total is partial if it can't be priced.
- **Usage that can't be carried over** (the target bills a different kind of unit): the service is
  flagged as unpriceable with the reason, as 024 does, and the total is partial.
- **Reserved or committed terms on the source**: the target uses on-demand pricing unless the user
  chooses a commitment the target offers; the agent says which term it used and why.
- **Very large architectures**: a translation holds at most 100 items (collections, services and
  connectors), as 025's proposals do; a larger source is declined with its size, and nothing is
  proposed.
- **The source is already on the target provider**: the agent says there's nothing to translate.
- **A direction not offered yet** (from GCP or Azure, or to several providers at once): the agent
  says it can't yet, and lists what it can do.
- **The source architecture or the mapping data changes while a translation is pending**: the
  proposal is marked stale and must be checked again and re-priced before it can be accepted.
- **No architecture is named and none is open**: the agent asks which one.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Translation MUST use the app's mapping data, and MUST record for every source
  service its match quality, where the match came from (seeded, automatic, or chosen by the
  user), its assumptions, and the mapping data version used. A mapping is for a kind of product
  (an instance type, database class or storage class) and holds in every region; prices come from
  the chosen target region, and where the matched product isn't sold there, the service is
  flagged and left out (FR-003).
- **FR-002**: Mappings MUST be found automatically where no seed mapping exists, from each
  product's category and attributes in the catalog. Exact and close matches (024's match quality)
  MAY be used without asking; where several qualify, FR-008 decides which one is used.
- **FR-003**: The agent MUST flag every service with no candidate, leave it out of the new
  architecture and its total, and label the total partial. It MUST NOT substitute an unverified
  service.
- **FR-004**: Where a service's only candidates are partial matches, the agent MUST show them with
  their differences and MUST use one only if the user chooses it; otherwise the service is left
  out as in FR-003. A chosen partial match MUST be marked "chosen by you" in the mapping table,
  MUST be named in every cost answer about the translation, and applies to that proposal only;
  the mapping data MUST NOT change.
- **FR-005**: The original architecture MUST NOT be modified.
- **FR-006**: The proposal MUST keep the original's collections, nesting and connections.
- **FR-007**: The proposal MUST show a mapping table with one row per source service, and the
  original's and the translation's totals for the same duration, with the difference in amount
  and percentage and the main drivers, all from the pricing engine.
- **FR-008**: Where several valid equivalents exist, the user MUST choose, or accept a stated
  default: the best match quality, then the lowest price.
- **FR-009**: Nothing MAY be saved until the user explicitly accepts; accepting MUST create a new
  architecture on the target provider, private and owned by the user, with exactly the proposed
  contents. Undo and Redo MUST work as for a new architecture in 025.
- **FR-010**: The agent MUST state its assumptions about regions (saying which are guesses),
  pricing term and sizing.
- **FR-011**: Translation MUST be offered from AWS to GCP and from AWS to Azure. For any other
  direction, or several targets in one request, the agent MUST say it can't yet and list what it
  can do.
- **FR-012**: A pending translation MUST be marked stale if its source architecture or the mapping
  data it used changes, and MUST be checked again and re-priced before it can be accepted.
- **FR-013**: Usage MUST be carried over only where 024's rules allow it (the same kind of
  billing unit); machine sizes MUST be matched to at least the source's vCPU and memory. A
  service whose usage can't be carried over MUST be flagged as unpriceable with the reason.
- **FR-014**: A source service that is unpriceable in the original MUST be flagged as such and
  MUST NOT be shown as a saving.
- **FR-015**: Asked which provider is cheaper, the agent MUST answer from the two totals and MUST
  state every caveat that applies (left-out or unmatched services, a partial total, matches that
  aren't exact including partial matches the user chose, differing terms or regions).
- **FR-016**: The matches 022 made for the four AWS standard architectures (to GCP and to Azure)
  MUST be available as seed mappings from the first release.
- **FR-017**: Every translation, refinement (including a chosen partial match), acceptance,
  rejection, undo and redo MUST appear in the activity log (023), with the mapping data version
  and the pricing snapshots behind its figures.

### Key Entities *(include if feature involves data)*

- **Service Mapping**: from one kind of source product (provider, service, and the attributes
  that identify it, such as an instance type; not a region) to its equivalent on a target
  provider, holding in every region: the matched product or "no equivalent", its assumptions,
  and a version. Seed mappings (from 022) are stored and versioned; automatic matches are
  worked out from the current pricing data each time, with their match quality and
  differences, and are not stored.
- **Translation Proposal**: a 025 proposal to create a new architecture, with its source
  architecture, target provider, target regions, the mapping data version used, the user's
  choices (among valid equivalents, and of partial matches), and its mapping table.
- **Mapping Table Row**: one source service in a translation: the source service, the match (or
  the reason there is none), match quality, where the match came from (seeded, automatic, or
  chosen by the user), assumptions, and the cost on each side.
- **Cost Difference Summary**: the original's and the translation's totals for the same duration,
  the difference in amount and percentage, the main drivers, and whether either total is partial,
  with the pricing snapshot of each provider.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of source services in every translation are matched (seeded, automatic, or
  chosen by the user) or flagged as having no equivalent.
- **SC-002**: 100% of translations with left-out, unmatched or unpriceable services disclose them
  and label the total partial, and 100% of partial matches used were chosen by the user and are
  named in every cost answer.
- **SC-003**: 100% of totals, differences and percentages in translations match the pricing
  engine's results to the cent.
- **SC-004**: The original architecture is unchanged in 100% of test cases, across propose,
  accept, reject, undo and redo.
- **SC-005**: All golden conversations pass on Claude Haiku 5.5, the one model this feature is
  checked against. Results on other models may be reported but aren't required.
- **SC-006**: Each of the four AWS standard architectures translates to GCP and to Azure with
  every service matched, except those 022 left out, which are flagged with 022's reason.
- **SC-007**: A user can go from asking for a translation of a standard architecture to an
  accepted, priced translation in at most three messages and under five minutes.

## Assumptions

- **Pricing data** for the source and target providers is available; a provider or region
  without data is handled as in 024 (said, never estimated).
- **Seed mappings**: 022's component matches give seed mappings for the services in the four
  standard architectures. The automatic matcher covers the other common kinds (compute, managed
  databases, object and block storage, load balancing, data transfer) using 024's catalog search
  and match-quality rules.
- **Regions**: no curated region matching. The user names target regions; otherwise the agent
  uses 024's nearest-region guess, says it is a guess, and asks to confirm.
- **Pricing term**: the target uses on-demand pricing unless the user picks a commitment the
  target provider offers, because reserved and committed terms don't correspond across providers.
- **Names**: the new architecture keeps the original's name unless the user gives one; it is
  already listed under the target provider, so nothing is added to the name. Names aren't
  checked for clashes, as in 025.
- **Sources**: any architecture the user can open, their own or a public one; the result is
  always the user's own private architecture.
- **Evaluation model**: golden conversations are checked live on Claude Haiku 5.5 only, as for
  025, to keep the cost of testing low; the input's "at least two configured models" is left to a
  later release.
- **No Admin review**: the input's Admin review queue is replaced by the user's choice in the
  conversation. Mapping data changes only with a release (seed mappings) or new pricing data
  (automatic matches).
- **Release**: pre-1.0, as the agent features before it.

## Out of Scope

- Directions other than AWS → GCP and AWS → Azure, and several targets in one request (a later
  release).
- An Admin review queue, Admin editing of mappings, and remembering a user's choices for later
  translations (possible later releases).
- Migration planning, infrastructure-as-code generation, negotiated discounts, importing existing
  infrastructure, and curated region matching.
- A Compare tab, and an Agent tab for users with no architectures yet.
- Changing the mapping data from the conversation (users change only their proposal).
- Box layout of the new architecture beyond the automatic placement 025 uses.
