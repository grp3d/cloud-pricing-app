# Research: Agent-Built Architectures (Create and Change)

Decisions for 025. Each lists what was chosen, why, and what else was considered. The spec has no
open clarifications; these settle the technical questions the plan raised.

## R1. One set of edit rules for manual and agent changes

**Decision**: move the rules the edit routes check inline today (`api/collections.py`,
`api/sku_selections.py`, `api/connectors.py`, `api/architectures.py`) into a new service module,
`src/services/architecture_rules.py`, as functions over a plain **architecture state** (R2):
nesting (an Application only inside a VPC, same region), region availability, region lock (a
collection with content keeps its region), connector ends in the same architecture and not the
same collection, names, and `validate_selection`'s price-type, purchase-option and
provider-options checks. The routes call these functions and keep their HTTP errors and messages;
proposals call the same functions on the proposed state.

**Rationale**: FR-002 and SC-003 need "the same validation as manual edits". One set of functions
used by both paths makes that true by construction, and the existing route tests guard the
refactor. Validating a whole proposed state at once also catches problems between items (a
service added to a collection that the same proposal removes).

**Alternatives considered**:
- *Apply the proposal through the routes' code inside a savepoint and roll back*: validates by
  construction too, but writes to the database on every proposal and refinement, mixes pricing
  with transaction state, and the routes commit inside their handlers.
- *A separate validator for proposals*: two rule sets would drift; rejected.

## R2. Architecture state, fingerprint and the applier

**Decision**: a pydantic `ArchitectureState` holds an architecture's content with row ids: name,
provider, collections (id, type, name, region, parent, created_at), services (id, collection or
connector, service code, SKU, term, purchase option, quantity, provider options, created_at) and
connectors (id, ends, arrow style, reversed). Three functions in
`src/services/architecture_state.py`:

- `read_state(architecture)` from the ORM rows (live rows only);
- `fingerprint(state)`: SHA-256 of the state's canonical JSON (sorted keys and ids);
- `apply_state(session, architecture, target)`: makes the saved rows equal `target`, keeping ids:
  updates changed rows, inserts rows that are missing (with their ids and `created_at`), and
  removes rows not in `target` (soft delete for collections and connectors as today, delete for
  services). One transaction.

A proposal is priced and validated as a target state; accepting applies it; undo applies the
saved "before" state and redo the "after" state.

**Rationale**: one mechanism covers accept, undo and redo, and makes "restores exactly" (FR-005,
SC-004) testable as `read_state(after undo) == before`. Keeping ids keeps the browser's box
layout, which is keyed by row id, and the activity log's references. The fingerprint detects any
saved change without touching every edit route (R3).

**Alternatives considered**:
- *Inverse operations per change item*: every item type needs its own inverse, and a missed
  side effect breaks exactness.
- *Rebuild from the export format* (`build_architecture`): new ids would lose the user's layout
  and break links to the architecture.

## R3. Detecting manual edits and stale proposals

**Decision**: compare fingerprints when they matter:

- a proposal stores the fingerprint of the state it was built on; it's **stale** when the current
  fingerprint differs (FR-007). Accepting a stale proposal re-validates and re-prices it against
  the current state first; if it still applies, the user sees the new figures and accepts again;
  if not, it can't be accepted;
- an accepted proposal stores the fingerprints of its before and after states. Undo is available
  only while the current fingerprint equals "after", and redo only while it equals "before";
  otherwise undo has **ended**, with the reason `edited` (FR-006). The name is part of the state;
  `is_public` and layout aren't (clarification Q3).

The frontend learns of the end through the session query it already refetches after every
architecture mutation, and shows the notice once, when the status flips to `edited`.

**Rationale**: works for edits from any tab or device and needs no hooks in the edit routes.

**Alternatives considered**: a flag set by every edit route (each route must remember to call it,
and a new route that doesn't silently breaks undo); database triggers (hard to test, outside the
app's patterns).

## R4. Operations the model gets

**Decision**: seven new operations in the 023 registry, plus 024's `search_products` and
`list_regions` unchanged:

| Operation | Purpose |
|---|---|
| `list_my_architectures` | The user's own architectures (name, provider, regions, size), to resolve a named one (edge case: missing or several). |
| `open_architecture` | Ask the app to open one of the user's architectures (FR-017). |
| `find_products` | Batch catalog search: up to 8 parts (category, function, words) in one provider and region, returning `C…` references. |
| `find_region_equivalents` | For given services (`V…` refs), the same product in another region of the same provider, with match quality; "none" where the catalog has none (GC-4). |
| `propose_changes` | Change items for the open architecture → a priced, validated proposal. |
| `propose_new_architecture` | A whole new architecture → a priced, validated proposal. |
| `propose_import` | A public architecture (from `list_importable_architectures`) and a name → an import proposal. |

`describe_open_architecture` now also gives each collection, service and connector a short
reference (`A…`, `V…`, `K…`) that lasts for the message, like 024's references. A pending proposal
is described the same way (items get `P…` references), so a refinement in a later message can
refer to it.

The model never sends ids or SKUs: only references, quantities, terms, names and regions
(Principle VII, FR-002).

**Rationale**: 023's round limit is 6 model calls per message. A new three-tier architecture needs
several products; a batch search keeps it at three rounds (search, propose, answer). The proposal
operations return the validation result, so the model can fix a rejected item within the message.

**Alternatives considered**: raising the round limit (more cost per message, Principle VIII);
one generic `edit` operation (harder for small models to fill correctly, and harder to check).

## R5. The proposal is a document, the cost is the engine's

**Decision**: a proposal stores its change items, the target state, the base fingerprint, the
assumptions the model stated, and a **cost summary** built by the app:

- the before and after totals from `calculate_architecture_price` over the current state and over
  the target state (an in-memory ORM graph built from the state, never added to the session, as
  `build_transient_architecture` does), for the duration the user asked (1 month by default);
- the difference and percentage, by service and by region, computed by the app (024 R7);
- unpriceable items, with the total labelled partial;
- **per-change contributions** (US8): changes are grouped by the user's request as the model
  labels them; each group's contribution is the change in total when it's applied after the
  groups before it, in order, so the contributions add up to the total difference exactly.

Figures reach the model as references only, as in 023 and 024 (FR-004, SC-001).

**Rationale**: the same engine as the Pricing tab, no writes before acceptance (FR-003), and exact
sums for US8. Group order is shown with the contributions.

**Alternatives considered**: each group priced alone against "before" (contributions don't add up
when prices are tiered); storing only the items and recomputing the target on accept (a stale base
would change what's applied without the user seeing it).

## R6. Proposal lifecycle and undo scope

**Decision**:

- states: `pending` → `accepted` | `rejected` | `superseded` (a later proposal in the session
  replaces it) | `expired` (session ended); a pending proposal can also be **stale** (R3),
  computed rather than stored;
- one pending proposal per session; a refinement or a new request supersedes it;
- only the **latest accepted** proposal in the session can be undone or redone. Accepting another
  one ends the earlier one's undo (reason `superseded`);
- accept, reject, undo and redo are REST actions by the user: no model call, no message from the
  allowance, and they still work after a limit is reached (FR-016). They are refused while a
  message is being answered in the session (409), so a proposal can't change under a running
  answer;
- a proposal can be accepted only while its architecture is open in the request (`architecture_id`
  in the action body must match) (edge case: switching architectures);
- creating and importing: accept builds the new architecture with `build_architecture`; undo soft
  deletes it (`deleted_at`) and redo restores it with the same ids;
- at most 100 change items per proposal (edge case: very large); `propose_*` returns a tool error
  above that, and the model offers to build in parts.

**Rationale**: matches the spec and clarifications exactly; soft delete keeps undo and redo of a
creation exact and cheap.

## R7. Opening a named architecture and unsaved work

**Decision**: `open_architecture` checks ownership and returns at once; the stream sends an
`open_architecture` event. The frontend then:

1. asks the workspace whether anything is unsaved (a new small `unsavedWork` registry that the
   Service tab, the Architecture Editor's name fields and the connector form register with);
2. if so, shows a dialog: "You have unsaved changes in '<name>'." with **Save and continue** and
   **Discard and continue**; nothing opens until the user chooses. If saving fails validation, the
   app says why and keeps the current architecture open;
3. opens the architecture, as picking it in the menu does.

The session follows the open architecture (023), so the next message is about it. A proposal the
model makes in the same message is for the named architecture (the operation tells the model its
references); it can be accepted only once that architecture is open (R6).

**Rationale**: the server can't wait on a dialog mid-answer without holding the model call open;
this way the user still sees the architecture open before acting on the proposal, and saving is
an ordinary manual edit (FR-006, FR-017).

**Alternatives considered**: pausing the answer until the dialog closes (holds a model stream open
for an unbounded time); refusing to work on a closed architecture (clarification Q4 chose
opening).

## R8. Where proposals appear

**Decision**: proposals are a second kind of item in 024's Results pane and its ◀ ▶ sequence,
in creation order with results. The pane shows: the status (pending, stale, accepted, rejected,
superseded), the change list grouped by added, changed and removed, the before and after table by
service and by region, contributions, unpriceable items, assumptions, and the actions. Undo and
Redo appear on the accepted proposal in the pane and on its card in the conversation, with the
reason when undo has ended (clarification Q2). The canvas shows saved work only (clarification
Q1). There's no CSV for proposals in this release.

## R9. Activity log

**Decision**: accepting, rejecting, undo and redo add rows to the activity log (`agent_operations`)
named `accept_proposal`, `reject_proposal`, `undo_proposal` and `redo_proposal`, linked to the
proposal's message, with the architecture, the item count and the snapshot of the figures
(FR-014). They're shown as the user's actions.

## R10. Prompt and evaluation

**Decision**:

- prompt v025.1 adds: what the agent can change; propose, never claim to have saved; ask at most
  three questions, then offer defaults; one batch search, then propose; replicate only through
  `find_region_equivalents`; say when something isn't in the catalog; never change an
  architecture that isn't the user's (offer an import);
- golden conversations GC-1 to GC-10 become eval cases `gc-19` to `gc-28`. The runner gains
  proposal checks: the proposal kind and item counts, validation passed, every figure equal to
  the engine's, nothing saved before acceptance, and scripted user actions (accept, reject, undo,
  redo, a manual edit) with state checks after each;
- live runs: Claude Haiku 5.5 only (SC-006), under the paid-usage rules in `CLAUDE.md`.

**SC-007** ("description to an accepted, priced architecture in under 5 minutes") is measured in
the quickstart: GC-1 and GC-3 together need at most 3 user messages, each answered within the
agent timeout, on Haiku.

## R11. Storage

**Decision**: migration `0012_agent_proposals` adds `agent_proposals`: id, session (cascade
delete), message, seq (per session; the pane orders proposals and 024's results together by creation
time), kind (`change`,
`create`, `import`), architecture (null until a create or import is accepted), status, title,
items (JSONB), base state, target state, base fingerprint, cost summary (JSONB), assumptions
(JSONB), the accepted before and after fingerprints, undo status (`available`, `undone`, `ended`),
end reason, and timestamps.

**Principle II note**: the cost summary is a record of what was shown, with its snapshot, as
`agent_results` is in 024. Nothing prices from it: an accept re-prices when the proposal is stale.
