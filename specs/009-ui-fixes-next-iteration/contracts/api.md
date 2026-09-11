# API Contracts: UI Fixes and Enhancements — Next Iteration

Only endpoints that change. Every other endpoint (architectures, collections, calculate,
sku-selections, providers) is untouched by this feature. Per Constitution Principle IV, both
changes below are Pydantic-modeled so `check-api-types` generates matching TypeScript types —
no untyped/ad-hoc shape crosses the boundary.

## 1. `POST /connectors/{connector_id}/sku-selection` — behavior change, no schema change

**Request** (`SKUSelectionCreate`) and **success response** (`SKUSelectionOut`, `201`):
unchanged.

**New behavior**: when the target Connector already has a `SKUSelection`, the endpoint no
longer deletes it and inserts the new one. It now returns:

```
409 Conflict
{
  "detail": "This Connector already has a Service. Create a new Connector to add another."
}
```

using FastAPI's standard `HTTPException(status_code=409, detail=...)` — this codebase's
existing error-response convention (see `create_connector`'s existing `400` for a self-link
attempt in the same file). No new Pydantic error schema; `frontend/src/api/client.ts`'s
`request()` already surfaces `detail` as `Error.message` for any non-2xx response, so no
frontend contract change is needed to consume this.

```python
@router.post("/connectors/{connector_id}/sku-selection", response_model=SKUSelectionOut, status_code=201)
async def attach_connector_sku(...) -> SKUSelectionOut:
    connector = await get_owned_connector(connector_id, session, user)
    if connector.sku_selection is not None:
        raise HTTPException(
            status_code=409,
            detail="This Connector already has a Service. Create a new Connector to add another.",
        )
    # ... existing insert logic, unchanged, minus the now-dead delete-existing branch
```

## 2. `GET /catalog/skus` — two new optional query parameters

**Request** (`search_skus`'s existing query-param signature): two additions, both optional,
both following the existing regex-filter convention (008, FR-020):

| Parameter | Type | Default | Behavior |
|---|---|---|---|
| `from_region_code` | `str \| None` | `None` | Case-insensitive RE2 regex against `attributes_json.fromRegionCode`. |
| `to_region_code` | `str \| None` | `None` | Case-insensitive RE2 regex against `attributes_json.toRegionCode`. |

`search_catalog()`'s signature grows the same two parameters, AND-combined into the existing
`where`/`params` construction using
`regexp_matches(json_extract_string(p.attributes_json, '$.fromRegionCode'), ?, 'i')` (and the
`toRegionCode` counterpart) — same pattern every existing filter clause already uses. The
`EmptyCatalogFilterError` guard's `any([...])` check grows to include these two, so a search
with only a region-code filter set is valid (doesn't require also setting `service_code` etc.).

**Response** (`CatalogSearchResult`): **unchanged.** The derived AWSDataTransfer display label
is computed frontend-side from `CatalogSKUOut.attributes` (already includes
`fromRegionCode`/`toRegionCode` via `parse_attributes()`'s existing flatten-everything
behavior) — no new response field.

```python
def search_catalog(
    *,
    service_code: str | None = None,
    product_family: str | None = None,
    text: str | None = None,
    from_region_code: str | None = None,   # NEW
    to_region_code: str | None = None,     # NEW
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], str, int]:
    if not any([service_code, product_family, text, from_region_code, to_region_code]):
        raise EmptyCatalogFilterError(...)
    ...
    if from_region_code:
        where.append("regexp_matches(json_extract_string(p.attributes_json, '$.fromRegionCode'), ?, 'i')")
        params.append(from_region_code)
    if to_region_code:
        where.append("regexp_matches(json_extract_string(p.attributes_json, '$.toRegionCode'), ?, 'i')")
        params.append(to_region_code)
    ...
```

## Frontend-only contract: `lib/priceChange.ts`'s `BaselineDecision`

Not a network contract, but a shared type/behavior contract between `priceChange.ts` and its
one caller (`WorkspacePage.tsx`) worth calling out here since it's the mechanism FR-002/003
depend on: `BaselineDecision` gains a `"duration_only"` member (data-model.md). Any
exhaustiveness switch over `BaselineDecision` in `WorkspacePage.tsx` must add a case for it —
TypeScript's own exhaustiveness checking (a `never` default case, if present) makes omitting it
a compile error, not a silent runtime gap.
