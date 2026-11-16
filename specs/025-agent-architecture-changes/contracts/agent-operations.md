# Contract: Agent Operations Added in 025

Registered in the 023 registry (`src/agent/operations_change.py`). They take the user, the open
architecture and the session from `OperationContext`, never from the model. None of them saves
an architecture: the `propose_*` operations create proposals, which only the user's accept
saves (FR-003, Principle VII).

Results go to the model as JSON data. Amounts are figure references (`F…`); products are
references (`C…` from searches); existing rows are references (`A…` collections, `V…`
services, `K…` connectors, `P…` proposal items). References last for one message. The model
never sees or sends ids or SKUs.

## Changes to existing operations

- `describe_open_architecture`: each collection, service and connector gains its reference, and
  the output says whether the user owns the architecture.
- `list_importable_architectures` (023): each entry gains a reference (`I…`) for `propose_import`.

## `list_my_architectures`

Input: `{}`. Output: the user's own architectures, each `{ref: "M1", name, provider, regions,
services, is_open}`. Used to resolve a named architecture (missing or several matches).

## `open_architecture`

Input: `{"architecture": "M2"}`. Checks ownership, then asks the app to open it (stream event
`open_architecture`, agent-api.md). Output: `{opened: "Prod Web", references: {...}}` with the
same references `describe_open_architecture` gives, so a proposal can follow in the same
message. Errors: not found; not the user's.

## `find_products`

Batch catalog search in one provider and region (R4).

```json
{
  "provider": "gcp",
  "region": "us-central1",
  "parts": [                                   // 1–8
    {"part": "web", "category": "compute", "function": "virtual_machine", "text": "e2"},
    {"part": "db", "category": "database", "text": "postgres"},
    {"part": "files", "category": "storage", "function": "object_storage"}
  ]
}
```

Output: per part, up to 5 candidates `{ref: "C4", product, attributes, billing_unit}`, or
`none` with the reason. Same catalog search as 024's `search_products`.

## `find_region_equivalents`

```json
{"services": ["V1", "V3", "V4"], "region": "us-west-2"}
```

Output: per service, the same product in the target region `{ref: "C9", quality: "exact"|"close",
differences}` or `none` with the reason (GC-4). Same provider only. Errors: the region equals the
source region, or the provider doesn't offer it.

## `propose_changes`

For the open architecture, or the one just opened. Replaces any pending proposal in the session.

```json
{
  "title": "Replicate Prod Web to us-west-2",
  "duration": "1_month",
  "changes": [                                  // 1–100 items in total
    {"group": "standby", "op": "add", "collection": {"ref": "new1", "type": "vpc",
      "name": "Prod Web standby", "region": "us-west-2"}},
    {"group": "standby", "op": "add", "service": {"in": "new1", "product": "C9",
      "quantity": 744, "term": "on_demand"}},
    {"group": "replication", "op": "add", "connector": {"from": "A1", "to": "new1",
      "product": "C12", "quantity": 500, "arrow": "one_way"}},
    {"group": "resize", "op": "change", "service": {"ref": "V2", "quantity": 372}},
    {"group": "cleanup", "op": "remove", "ref": "V7"}
  ],
  "assumptions": [
    {"kind": "usage", "text": "500 GB a month of data change"},
    {"kind": "region", "text": "us-west-2 for the standby", "guessed": true}
  ]
}
```

- `in`, `from`, `to` take `A…` references or `new…` refs from earlier items in the same call.
- `product` takes a `C…` reference from this message; `change` may also set `term`,
  `purchase_option`, `product` (a resize) or a collection's `name`.
- Output on success: `{proposal: "Q3", items, cost: {before: F1, after: F2, difference: F3,
  percent: F4, partial, by_service, by_region, contributions, unpriceable}, stale: false}`.
- Validation failure: a tool error naming the first failing item and rule (data-model.md
  validation rules), so the model can fix it in the same message.
- Errors: not the user's architecture (the model offers an import); more than 100 items; no
  architecture open.

## `propose_new_architecture`

```json
{
  "name": "Three-tier web app",
  "provider": "gcp",
  "duration": "1_month",
  "collections": [{"ref": "new1", "type": "vpc", "name": "Web VPC", "region": "us-central1"}],
  "services": [{"in": "new1", "product": "C4", "quantity": 1488, "term": "on_demand",
                "group": "web tier"}],
  "connectors": [],
  "assumptions": [{"kind": "size", "text": "2 × e2-standard-2 for the web tier"}]
}
```

Output as for `propose_changes`, with no before figures. Errors: any validation failure.

## `propose_import`

Input: `{"architecture": "I2", "name": "My Serverless Microservices Back-End"}` (name optional,
default "My <name>"). Output: the proposal with the copy's cost. Errors: not importable.

## Activity log

Every operation above is logged as in 023, with its inputs (references resolved to names and
SKUs in the summary) and the snapshot of any figures.
