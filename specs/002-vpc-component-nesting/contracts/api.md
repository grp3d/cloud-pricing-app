# Phase 1 API Contract: Nest Application Components into VPCs

This is a delta on `specs/001-assemble-price-aws-architecture/contracts/api.md` — one new
endpoint, one changed response shape. Every other endpoint in 001's contract is unchanged and not
repeated here. As in 001, the authoritative contract is the live OpenAPI schema FastAPI
generates; this document exists to trace the change back to its requirement before the code
exists.

## Changed: `CollectionOut` (used by `GET /architectures/{id}` and elsewhere)

Adds one field:

```json
{
  "id": "uuid",
  "type": "application_component" | "vpc",
  "name": "string",
  "parent_collection_id": "uuid" | null,
  "sku_selections": [ /* unchanged, see 001 */ ]
}
```

`parent_collection_id` is always `null` for a `type: "vpc"` Collection. For a
`type: "application_component"` Collection, it is the id of the VPC it's nested inside, or
`null` if it's top-level.

## New: `PATCH /collections/{id}`

Set, move, or clear an Application Component's nesting (spec FR-001, FR-002, FR-003).

**Request**:
```json
{ "parent_collection_id": "uuid" }
```
or, to un-nest:
```json
{ "parent_collection_id": null }
```

**Response** `200`: the updated Collection, in the same shape as `CollectionOut` above.

**Errors**:
- `400` — the target Collection (the one being nested) is itself `type: "vpc"` (spec FR-004: a
  VPC can never have a parent).
- `400` — `parent_collection_id` does not reference an existing, non-deleted `type: "vpc"`
  Collection belonging to the same Architecture as the Collection being nested (spec FR-001,
  FR-002).
- `404` — the Collection being nested does not exist, is soft-deleted, or is not owned by the
  caller (same ownership scoping as every other Collection endpoint in 001's contract).

Idempotent: setting the same `parent_collection_id` it already has, or `null` when it's already
`null`, succeeds and returns the unchanged Collection.
