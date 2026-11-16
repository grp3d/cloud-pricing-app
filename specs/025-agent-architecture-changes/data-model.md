# Data Model: Agent-Built Architectures (Create and Change)

Additions for 025. Existing tables (architectures, collections, sku_selections, data_connectors,
023's agent tables and 024's `agent_results`) are unchanged.

## 1. ArchitectureState (in memory and JSONB, not a table)

The saved content of one architecture, with row ids (research R2).

| Field | Notes |
|---|---|
| `name`, `provider` | Provider never changes within a proposal |
| `collections[]` | `id`, `type` (`vpc` / `application_component`), `name`, `region`, `parent_id`, `created_at` |
| `services[]` | `id`, `collection_id` or `connector_id` (exactly one), `service_code`, `sku`, `pricing_term`, `purchase_option`, `usage_quantity` (decimal string), `provider_options`, `created_at` |
| `connectors[]` | `id`, `from_id`, `to_id`, `arrow_style`, `arrow_reversed` |

- Only live rows (no `deleted_at`). `is_public`, owner and browser layout aren't part of it.
- **Fingerprint**: SHA-256 of the canonical JSON (keys sorted, lists sorted by id).
- **Completeness rule**: every saved column of these rows except timestamps of last update is in
  the state; a unit test compares the state's fields with the ORM columns.
- New rows in a proposal get their ids when the proposal is built, so the after state is exact.

## 2. Change Item (JSONB inside a proposal)

| Field | Notes |
|---|---|
| `ref` | `P1`, `P2`, … within the proposal |
| `op` | `add` / `change` / `remove` |
| `target` | `collection` / `service` / `connector` / `architecture` (name only) |
| `id` | The row's id (existing row, or the id given to a new one) |
| `before`, `after` | The row's fields before and after (absent for add / remove respectively) |
| `group` | The request part it belongs to (for contributions, US8), as the model labels it |
| `label` | Readable name, e.g. "Cloud SQL for PostgreSQL in us-central1" |

At most 100 items per proposal.

## 3. Cost Summary (JSONB inside a proposal)

| Field | Notes |
|---|---|
| `duration` | `1_day` / `1_month` / `1_year` |
| `snapshot` | Provider, date and revision |
| `before`, `after` | Total, `partial` flag; `before` is absent for a create or import |
| `difference`, `percent` | App figures from unrounded totals; absent for a create or import |
| `by_service[]` | Label, before, after, difference |
| `by_region[]` | Region, before, after, difference |
| `contributions[]` | Group, difference, in the order applied (they sum to the total difference) |
| `unpriceable[]` | Label, reason |

Amounts are decimal strings, unrounded; the UI rounds to the cent.

## 4. AgentProposal (table `agent_proposals`, migration 0012)

| Column | Type | Notes |
|---|---|---|
| `id` | uuid pk | |
| `session_id` | uuid fk → agent_sessions, cascade delete | |
| `message_id` | uuid fk → agent_messages | The user message it answers |
| `seq` | int | Unique per session |
| `kind` | `change` / `create` / `import` | Check constraint |
| `architecture_id` | uuid, nullable | The changed architecture; for create/import, set on accept |
| `source_architecture_id` | uuid, nullable | Import only |
| `title` | text | E.g. "Replicate Prod Web to us-west-2" or the new name |
| `status` | `pending` / `accepted` / `rejected` / `superseded` / `expired` | Check constraint |
| `items` | JSONB | Change Items (§2) |
| `base_state`, `target_state` | JSONB | ArchitectureState (§1); `base_state` null for create/import |
| `base_fingerprint` | text, nullable | For staleness (R3) |
| `cost` | JSONB | Cost Summary (§3) |
| `assumptions` | JSONB | List of `{kind: region/term/size/usage/default, text, guessed}` |
| `before_fingerprint`, `after_fingerprint` | text, nullable | Set on accept |
| `undo_status` | `available` / `undone` / `ended`, nullable | Null until accepted |
| `undo_end_reason` | `edited` / `superseded` / `session_ended` / `deleted`, nullable | |
| `created_at`, `decided_at` | timestamptz | |

Indexes: `(session_id, seq)` unique; `(session_id, status)`.

### State transitions

```text
pending ──accept──▶ accepted (undo_status = available)
pending ──reject──▶ rejected
pending ──new proposal in session──▶ superseded
pending ──session ends──▶ expired
accepted, available ──undo──▶ undone ──redo──▶ available
available/undone ──manual edit (fingerprint differs)──▶ ended (edited)
available/undone ──later proposal accepted──▶ ended (superseded)
any ──session deleted──▶ row deleted (cascade)
```

- **Stale** is computed, not stored: `pending` and the architecture's current fingerprint differs
  from `base_fingerprint`.
- **Undo available** only while the current fingerprint equals `after_fingerprint`; **redo** only
  while it equals `before_fingerprint` (R3). An architecture the user deleted ends undo
  (`deleted`).
- One `pending` proposal per session (enforced in the service, checked by a test).

## 5. Activity log rows

`agent_operations` rows named `accept_proposal`, `reject_proposal`, `undo_proposal`,
`redo_proposal`, with `inputs = {proposal_id, architecture_id}`, `summary = {items, title}`,
`snapshot` = the proposal's snapshot (R9).

## Validation rules (FR-002)

Applied to the target state by `architecture_rules` (R1), the same functions the edit routes use:

1. Provider has an adapter; every region is available for it.
2. Nesting: only an Application may have a parent; the parent is a VPC in the same architecture
   and region.
3. Region lock: an existing collection with content keeps its region.
4. Connectors join two different collections of the architecture.
5. Every service's SKU exists in its region's pricing data; price type, purchase option and
   provider options are valid for the provider and item.
6. At most 100 change items.

Names aren't checked for clashes: manual creation and the menu's Import allow a name the user
already has, so proposals do too (same rules as manual edits).

The first failure is returned to the model as a tool error with the item's reference, and the
proposal isn't created.
