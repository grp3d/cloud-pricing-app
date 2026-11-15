# Feature Specification: Agent-Built Architectures (Create and Change)

**Feature Branch**: `025-agent-architecture-changes`

**Created**: 2026-11-15

**Status**: Draft

**Input**: User description: "../speckit-inputs/agent-03-architecture-changes.md" (agent feature 3
of 4; builds on 023, the agent foundation, and 024, pricing questions and comparisons; follows
constitution 1.2.0, Principles I, III, V, VII and VIII)

## Overview

A user asks the agent, in plain language, to create a new architecture ("a three-tier web app on
GCP in us-central1"), to change one ("add replication of 'Prod Web' to another region", "make the
database half the size"), or to import a public architecture as their own copy. The agent asks
the follow-up questions it must, then proposes the result as a **proposal**: a reviewable set of
changes (or a new architecture), priced by the pricing engine. Nothing is saved until the user
accepts. Everything accepted in response to one user message can be undone in one action, and
redone.

**Why:** building or restructuring an architecture by hand means knowing what to add, choosing the
right SKUs, connecting them, and then finding out what it costs. The agent does that work and
shows the cost, while the user keeps full control over what is saved.

**What the agent can do in this release:**

- create a new architecture;
- add collections, services and connectors;
- scale: change quantities, sizes and pricing terms;
- replicate components to another region;
- remove components, as part of a change;
- import a public architecture as the user's own private copy.

For anything else, the agent says plainly that it can't, and lists what it can do.

**Builds on 023 and 024.** The Agent tab, sessions, limits, the activity log, the evaluation set,
the Results pane and the rule that every figure comes from the pricing engine (the model refers to
figures; the app fills them in) all carry over unchanged. The answering rules of 024 (at most
three questions before offering defaults, stating assumptions, saying when a region is a guess,
never inventing a SKU) apply to proposals too.

## Clarifications

### Session 2026-11-15

- Q: Which models must the golden conversations pass on (SC-006)? → A: Claude Haiku 5.5 only,
  to keep the cost of testing low while the challenges of the agent are worked out; tuning for
  other models is left to later releases.
- Q: Should a proposal be shown only in the Results pane, or also previewed on the canvas? → A:
  Results pane only; the canvas shows only saved work.
- Q: Where are Undo and Redo offered? → A: On the accepted proposal: in the Results pane and on
  its card in the conversation.
- Q: Which of the user's own changes end undo? → A: Any saved change to the architecture
  (collections, services, connectors, their settings, or its name); making it public or private
  and box layout don't.
- Q: If the user names one of their architectures that isn't open, does the agent open it or ask
  the user to? → A: The agent says it's opening it, opens it and proposes there. If the open
  architecture has unsaved work, the user is told first and chooses "Save and continue" or
  "Discard and continue".

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create a new architecture through conversation (Priority: P1)

A user describes what they need. The agent talks it through: provider, regions, the main parts
(compute, database, storage, networking), scale and pricing term, asking only what it needs. It
then proposes a new architecture: its name, collections, services with real catalog SKUs, and
connectors, priced. Accepting creates it, private and owned by the user, and opens it.

**Why this priority**: creating from a description is the main new ability of this feature and
the one most users will try first.

**Independent Test**: for a set of descriptions, the proposal passes the same validation as manual
edits, uses only SKUs from the catalog, and its price equals the pricing engine's result for the
same architecture; accepting it creates exactly what was proposed.

**Acceptance Scenarios**:

1. **Given** a clear description, **When** the user sends it, **Then** the agent proposes a
   complete, priced architecture with its assumptions stated.
2. **Given** a vague description, **When** the user sends it, **Then** the agent first asks short,
   specific questions (at most three before offering defaults).
3. **Given** the agent has asked questions, **When** the user says "use your best defaults",
   **Then** the agent states the defaults it used and proposes.
4. **Given** a description that needs something the catalog has no SKU for, **When** the agent
   proposes, **Then** it says so and leaves that part out rather than inventing one.
5. **Given** a proposed new architecture, **When** the user accepts, **Then** it is created
   private and owned by the user, and it opens on the canvas with its boxes placed automatically.

---

### User Story 2 - Change an existing architecture (Priority: P1)

A user describes a change to the open architecture, or to one of theirs by name. The agent
identifies the affected components, asks only what it needs (for example the target region, which
data stores to replicate, standby size, expected data change volume, pricing term), then proposes
the additions, changes and removals as one pending proposal.

**Why this priority**: most architectures already exist; changing them with the cost impact shown
is the everyday use.

**Independent Test**: for a set of change requests on seeded architectures, the proposal lists
exactly the affected items, passes manual-edit validation, and accepting it produces the
architecture the proposal described.

**Acceptance Scenarios**:

1. **Given** a clear change request, **When** the user sends it, **Then** the agent proposes the
   additions, changes and removals as one pending proposal.
2. **Given** a request that leaves out needed details, **When** the user sends it, **Then** the
   agent asks short, specific questions first.
3. **Given** a request outside what the agent can do (for example "set up a cost alert"), **When**
   the user sends it, **Then** the agent says it can't and lists what it can do.
4. **Given** a request to replicate components to another region, **When** the agent proposes,
   **Then** the proposal adds the copies in the target region, with the connectors and the
   cross-region data transfer the replication needs, and states the sizing and data change volume
   it assumed.
5. **Given** the user names one of their architectures that isn't open, **When** the agent acts on
   it, **Then** it says it's opening that architecture, opens it, and proposes there.
6. **Given** the open architecture has unsaved work (for example Service tab input not yet
   saved), **When** the agent is about to open another one, **Then** the user is told and chooses
   "Save and continue" or "Discard and continue"; nothing opens until they choose.

---

### User Story 3 - Review the proposal and its cost (Priority: P1)

The proposal shows what will be added, changed and removed, and the cost before and after: the
total, the difference in amount and percentage, by service and by region. A new architecture shows
its cost only. The agent explains in plain language what drives the cost and lists anything that
couldn't be priced.

**Why this priority**: the user can only decide to accept with the changes and their cost in front
of them; this is what makes the agent's work safe to accept.

**Independent Test**: for each proposal in the test set, every before, after and difference figure
equals the pricing engine's result for the architecture before and after the change.

**Acceptance Scenarios**:

1. **Given** a change proposal, **When** it is shown, **Then** each change item is listed as added,
   changed or removed, and the before and after figures (total, difference, percentage, by service,
   by region) equal the pricing engine's results.
2. **Given** a proposal with items that can't be priced, **When** it is shown, **Then** they are
   named and the total is labelled partial.
3. **Given** a proposed new architecture, **When** it is shown, **Then** it shows its cost by
   service and by region, with no before figures.

---

### User Story 4 - Accept, reject, undo, redo (Priority: P1)

- Accepting saves the proposal and re-prices the architecture. Rejecting saves nothing.
- **Undo** reverses everything the agent changed in response to the user's latest message, as one
  unit: if one message led to 20 changes, undo reverses all 20. **Redo** applies them again. One
  level of each.
- If the user edits the architecture themselves afterwards, undo is no longer possible. The app
  says so at that moment, for example: "Your latest edit means the agent's previous change can no
  longer be undone."
- Undo is also unavailable once the session ends.

**Why this priority**: acceptance and a reliable undo are what let a user trust the agent with
their saved work.

**Independent Test**: accept a many-item proposal, undo, and compare the architecture with its
saved state before acceptance: they match exactly. Redo, and compare with the accepted state: they
match exactly.

**Acceptance Scenarios**:

1. **Given** a pending proposal, **When** the user rejects it, **Then** nothing in the
   architecture changes.
2. **Given** a pending proposal, **When** the user accepts it, **Then** exactly the proposed
   changes are saved, together, and the architecture's price is updated.
3. **Given** an accepted proposal of many changes, **When** the user selects Undo, **Then** the
   architecture matches its state before acceptance exactly; **When** the user then selects Redo,
   **Then** it matches the accepted state exactly.
4. **Given** an accepted proposal, **When** the user edits the architecture by hand, **Then** the
   app says undo is no longer possible, and Undo is unavailable.
5. **Given** an accepted proposal that created a new architecture, **When** the user selects Undo,
   **Then** the new architecture is removed; Redo creates it again.

---

### User Story 5 - Import a public architecture through the agent (Priority: P1)

The user asks to import one of the public architectures the agent can list (023). The agent
proposes the import with a name ("My <name>" by default). Accepting creates the user's own private
copy, exactly as the architecture menu's Import does.

**Why this priority**: importing a standard architecture is the quickest start for a new user, and
023 currently points them to the menu instead.

**Independent Test**: an import accepted through the agent produces the same copy (collections,
services, connectors, settings) as the menu's Import with the same name.

**Acceptance Scenarios**:

1. **Given** "Import the serverless back-end", **When** the agent proposes, **Then** it names the
   architecture it matched and proposes "My Serverless Microservices Back-End".
2. **Given** a proposed import, **When** the user accepts, **Then** a private copy owned by the user
   is created and opened.
3. **Given** a name that matches several public architectures, **When** the user asks to import,
   **Then** the agent lists the matches and asks which one.

---

### User Story 6 - Adjust the proposal in conversation (Priority: P2)

The user refines a pending proposal ("make the standby half the size"), and the agent updates the
proposal and its cost.

**Why this priority**: useful once proposals exist; without it the user rejects and asks again.

**Independent Test**: a refinement message produces an updated proposal that differs from the
previous one only in what was asked, with re-priced figures.

**Acceptance Scenarios**:

1. **Given** a pending proposal, **When** the user asks for a refinement, **Then** the agent
   replaces the pending proposal with an updated one, says what changed, and shows the new cost.

---

### User Story 7 - Preview without saving (Priority: P2)

A user asks a what-if ("what if I doubled the storage?") and sees the cost impact as a proposal
they don't have to accept. A public architecture the user doesn't own can't be changed; it can be
imported as their own copy (Story 5) and then changed.

**Why this priority**: what-ifs reuse the proposal with no new mechanics, and answer a common
question.

**Independent Test**: a what-if produces a proposal with before and after cost; leaving it
unaccepted leaves the architecture unchanged.

**Acceptance Scenarios**:

1. **Given** a what-if question, **When** the agent answers, **Then** it shows a proposal with the
   cost impact and says it won't be saved unless accepted.
2. **Given** a public architecture the user doesn't own is open, **When** they ask for a change,
   **Then** the agent says it can't change it and offers to import a copy first.

---

### User Story 8 - Several changes in one request (Priority: P3)

The agent handles a request with more than one change and shows each change's contribution to the
cost.

**Why this priority**: the single proposal already holds several items; showing per-change
contributions is a refinement.

**Independent Test**: a request with two distinct changes produces one proposal whose per-change
contributions add up to the total difference.

**Acceptance Scenarios**:

1. **Given** a request with several changes, **When** the agent proposes, **Then** each change's
   cost contribution is shown and they add up to the total difference.

---

### Golden conversations (seed for the evaluation set)

- **GC-1:** "Create a three-tier web app on GCP in us-central1." The agent asks about expected
  traffic or instance size, database engine and size, and storage. It then proposes a priced
  architecture with real SKUs.
- **GC-2:** "Change architecture 'Prod Web' to include replication to another region." The agent
  asks about the target region, which components to replicate, standby sizing and data change
  volume, then proposes the additions with before and after cost and the main drivers.
- **GC-3:** The user answers "use your best defaults." The agent states the defaults and proposes.
- **GC-4:** A component has no replication option in the catalog. The agent says so and doesn't
  invent one.
- **GC-5:** Cross-region data transfer can't be priced. It's shown as unpriceable, and the total is
  labelled partial.
- **GC-6:** The user rejects the proposal. Nothing changes.
- **GC-7:** One message leads to many changes; the user accepts, then undoes. The architecture
  matches its previous state exactly. Redo applies the changes again.
- **GC-8:** The user accepts, then edits a service by hand. The app says undo is no longer
  possible, and undo is unavailable.
- **GC-9:** "Import the serverless back-end." The agent proposes "My Serverless Microservices
  Back-End"; accepting creates a private copy.
- **GC-10:** "Set up a Kubernetes cost alert." The agent says it can't, and lists what it can do.

### Edge Cases

- **The named architecture is missing, or several match**: the agent says none matched, or lists
  the matches and asks which one. It never guesses between them.
- **The target region equals the source region, or the provider doesn't offer it**: the agent
  says so and asks for another region; it never proposes a replica in the same region.
- **The change interacts with reserved pricing terms**: a scaled or replicated service keeps its
  pricing term unless the user asks otherwise, and the agent says which term each new or changed
  service uses.
- **The user declines to answer follow-up questions**: the agent offers its stated defaults
  once; if the user still declines, it proposes nothing and says what it needs.
- **A request would create a very large architecture**: a proposal holds at most 100 change items;
  beyond that the agent says so and offers to build it in parts.
- **The architecture is edited while a proposal is pending**: the proposal is marked stale. Before
  it can be accepted it is checked again against the current architecture and re-priced; if it no
  longer applies, it can't be accepted and the agent offers to propose again.
- **Saving fails on "Save and continue"** (the unsaved work doesn't pass validation): the app says
  why, keeps the current architecture open, and the agent waits.
- **The user switches architectures while a proposal is pending**: the proposal stays with its
  architecture; it can be accepted or rejected only while that architecture is open.
- **The user's limits are reached part-way through a conversation**: accepting, rejecting, undo
  and redo still work, because they need no model call; new proposals and refinements stop, with
  the limit message from 023.
- **More than one proposal**: a session has at most one pending proposal; a refinement or a new
  request replaces the pending one, which is marked superseded.
- **Undo after a later agent message**: undo always covers the latest accepted message only; once a
  later message's proposal is accepted, the earlier one can no longer be undone.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The agent MUST ask for missing information before proposing, or offer stated
  defaults, asking at most three questions before offering defaults.
- **FR-002**: Every proposal MUST pass the same validation as manual edits (for example region
  locking and nesting rules) and MUST use only SKUs and settings the catalog supports. The agent
  MUST NOT name a SKU the catalog didn't return.
- **FR-003**: The system MUST show each proposal for review and MUST NOT save any part of it until
  the user explicitly accepts it. Rejecting MUST leave the architecture unchanged.
- **FR-004**: A change proposal MUST show before and after cost (total, difference in amount and
  percentage, by service, by region) from the pricing engine; a new architecture MUST show its
  cost by service and by region. Both MUST list unpriceable items and label the total partial
  when any exist.
- **FR-005**: Everything accepted in response to one user message MUST be saved together and be
  undoable, and then redoable, as one unit, one level each. Undo MUST restore the architecture to
  its saved state before acceptance exactly; undoing a created or imported architecture removes
  it. Undo and Redo MUST be offered on the accepted proposal, in the Results pane and on
  its card in the conversation; when undo is no longer possible, both places say why.
- **FR-006**: A manual edit to the architecture after an agent change MUST end the ability to undo
  that change, and the user MUST be told at that moment. An edit is any saved change to the
  architecture: its collections, services, connectors, their settings, or its name. Making it
  public or private, and box positions and other layout kept in the browser, are not edits.
- **FR-007**: A proposal MUST be marked stale if its architecture changes after the proposal was
  created, and MUST be checked again and re-priced before it can be accepted.
- **FR-008**: The agent MUST state the assumptions it made (regions, pricing term, sizing, usage)
  and say which regions are guesses.
- **FR-009**: A new or imported architecture MUST be private and owned by the user.
- **FR-010**: The agent MUST NOT change an architecture the user doesn't own; it MAY offer to
  import a copy.
- **FR-011**: For a request outside its abilities, the agent MUST say so and list what it can do.
- **FR-012**: An import through the agent MUST produce the same copy as the architecture menu's
  Import with the same name.
- **FR-013**: Undo MUST be unavailable once the session ends.
- **FR-014**: Every proposal, acceptance, rejection, undo and redo MUST appear in the activity log
  with its architecture, its change items and the pricing snapshot of its figures.
- **FR-015**: Proposals MUST appear in the Results pane beside the conversation, with a card under
  the answer that names the proposal and its cost difference; accept and reject are available
  from the proposal. The canvas MUST show only saved work: proposals are not drawn on it.
- **FR-016**: Accepting, rejecting, undo and redo MUST NOT use a message from the user's allowance
  or make a model call.
- **FR-017**: When the user names one of their architectures that isn't open, the agent MUST say
  it's opening it, and the app MUST open it. A proposal for that architecture MUST NOT be accepted
  until it is open. If the open architecture has unsaved work, the app MUST first tell the user and offer "Save and continue" or "Discard and
  continue", and open nothing until they choose. Saving this way is a manual edit (FR-006).

### Key Entities *(include if feature involves data)*

- **Proposal**: a pending set of change items for one architecture, or a new architecture to
  create or import. It belongs to one session and one architecture (or none, for a new one), and
  is pending, accepted, rejected, stale or superseded.
- **Change Item**: one addition, change or removal of a collection, service or connector, with its
  settings before and after.
- **Cost Summary**: the pricing engine's figures for the architecture before and after the
  proposal: totals, differences, by service, by region, with unpriceable items and the snapshot
  date.
- **Assumption**: a stated default or guess the proposal relies on (region, term, size, usage).
- **Undo Record**: the saved state of an architecture before an accepted proposal, tied to the
  user message it answered; it allows one undo and one redo, and ends with a manual edit, a later
  accepted proposal or the session's end.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of before, after and difference figures in proposals match the pricing engine's
  results to the cent.
- **SC-002**: 0 changes are saved without explicit acceptance, verified by automated tests over
  every proposal path, including stale and superseded proposals.
- **SC-003**: 100% of proposals in the test set pass manual-edit validation and use only catalog
  SKUs.
- **SC-004**: Accepting and then undoing restores the original architecture exactly in all test
  cases, and redo restores the accepted state exactly.
- **SC-005**: An import through the agent matches the menu's Import in all test cases.
- **SC-006**: All golden conversations pass on Claude Haiku 5.5, the one model this feature is
  checked against. Results on other models may be reported but aren't required.
- **SC-007**: A user can go from a description to an accepted, priced new architecture in under
  5 minutes in the golden conversations.

## Assumptions

- Changes are applied as validated operations on the saved architecture, as manual edits are
  (collections, services and connectors one at a time), and the whole of one acceptance is saved
  together or not at all. Undo needs the architecture's previous state saved before each accepted
  proposal.
- Box positions are kept in the browser, so boxes the agent adds are placed automatically; undo
  and redo don't restore layout.
- The catalog defines which configurations are valid; the agent finds SKUs through the same
  catalog search 024 uses.
- An architecture belongs to one provider; creating one on another provider than the user named,
  or translating between providers, is agent-04.
- Proposals are shown in the Results pane that 024 added; the canvas shows only saved state.
- Usage the agent assumes for new services (hours, GB, requests) uses the app's defaults, the same
  ones 024 uses, and is stated as an assumption.

## Out of Scope

Cross-cloud translation (agent-04); changes saved without acceptance; changes to pricing data;
more than one level of undo; changing architectures the user doesn't own; previews drawn on the
canvas; changes to box layout.
