# Quickstart: Validate Service Selection Improvements

This script validates the two backend-visible pieces (richer detail, units) via the API, and
describes the frontend smoke check for the two canvas behaviors (auto-fit, manual resize), which
are inherently visual. Builds on `001`'s and `002`'s quickstart setup — run those first if the
backend/frontend aren't already running.

## Prerequisites

Same as `001`/`002`: backend running against a migrated Postgres database (no new migration in
this feature), frontend running and proxying to it.

## Validate: richer SKU detail and units (User Stories 1-2)

```bash
BASE=http://localhost:8000/api/v1
AUTH=(-H "Authorization: Bearer $TOKEN")

# 1. Search returns attributes and unit per result (FR-001, FR-002, FR-004, FR-005).
curl -s "${AUTH[@]}" "$BASE/catalog/skus?service_code=AmazonEC2&product_family=Compute+Instance&q=t3.medium" | jq '.results[0]'
# Expect: .attributes is a non-empty object with keys like instanceType/vcpu/memory; .unit is a
# string like "Hrs" (or null only if this exact SKU truly has no price_fact row).

# 2. Add that SKU to a Collection, and confirm the returned SKU Selection also carries unit
#    (reuse an Architecture/Collection from 001's quickstart, or create fresh ones).
SKU=$(curl -s "${AUTH[@]}" "$BASE/catalog/skus?service_code=AmazonEC2&product_family=Compute+Instance&q=t3.medium&limit=1" | jq -r '.results[0].sku')
curl -s "${AUTH[@]}" -X POST "$BASE/collections/$COLL_ID/sku-selections" \
  -H 'Content-Type: application/json' \
  -d "{\"service_code\": \"AmazonEC2\", \"sku\": \"$SKU\", \"pricing_term\": \"on_demand\", \"purchase_option\": \"not_applicable\", \"usage_quantity\": 730}" | jq '.unit'
# Expect: the same unit string (e.g. "Hrs"), not null, not omitted.

# 3. Fetch the Architecture and confirm the same SKU Selection, nested inside it, also carries
#    unit — proving the batched tree-level resolution (research.md #3) works, not just the
#    single-object endpoints.
curl -s "${AUTH[@]}" "$BASE/architectures/$ARCH_ID" | jq '.collections[].sku_selections[].unit'
# Expect: every entry is a real unit string (or null only for a genuinely unpriceable SKU).

# 4. A SKU with no meaningful attributes shows an empty map, not null (FR-003) — search a
# service/product_family combination known to have sparse data, e.g.:
curl -s "${AUTH[@]}" "$BASE/catalog/skus?service_code=AmazonS3&q=Fee" | jq '.results[0].attributes'
# Expect: {} (empty object) rather than null, if this particular SKU has no attributes_json.
```

**Expected outcome**: every step above matches — richer detail and units are present everywhere
a SKU is shown or selected, with well-defined behavior when either is unavailable.

## Frontend smoke check (User Stories 1-4)

With both servers running:

1. On the landing/create-architecture flow, search the catalog for a service family with
   several similar results (e.g., EC2 Compute Instance). Confirm each result row shows more than
   just a name and one summary line, and that picking one shows its full attribute detail before
   entering pricing inputs.
2. With a SKU picked, confirm the usage-quantity field shows that SKU's actual unit (e.g.,
   "Hrs"), not an unlabeled number field. Edit an already-added SKU Selection's inputs and
   confirm the unit shows there too.
3. Add two or three services to an Application Component and confirm its box on the canvas
   lists them and grows to fit; remove one and confirm it shrinks back down. Create a component
   with zero services and confirm it shows a small empty state, not an oversized empty box.
4. Drag a VPC box's resize handle and confirm it resizes; do the same for an Application
   Component box. Nest an Application Component inside a manually-shrunk VPC and confirm the VPC
   grows back to at least fit it (FR-011) rather than clipping or hiding it.
