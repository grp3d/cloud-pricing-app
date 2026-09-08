# Quickstart: Validate Nest Application Components into VPCs

This script proves the feature's single user story end-to-end against the real API, before (or
alongside) UI testing. It builds directly on
`specs/001-assemble-price-aws-architecture/quickstart.md`'s setup — run that first if the
backend/frontend aren't already running.

## Prerequisites

Same as `001-assemble-price-aws-architecture/quickstart.md`: backend running with a migrated
Postgres database (including this feature's new `0002_collection_nesting` migration), frontend
running and proxying to it.

## Validate: nest, move, and un-nest (User Story 1)

```bash
BASE=http://localhost:8000/api/v1
AUTH=(-H "Authorization: Bearer $TOKEN")

# 1. Create an Architecture with one VPC and one Application Component, each with a SKU
#    (reuse specs/001.../quickstart.md steps 2-5 twice — once per Collection type).
ARCH_ID=...      # from POST /architectures
VPC_ID=...       # from POST /architectures/$ARCH_ID/collections {"type":"vpc", ...}
APP_ID=...       # from POST /architectures/$ARCH_ID/collections {"type":"application_component", ...}
# Add at least one SKU Selection to APP_ID (per 001's quickstart step 5) and note the
# Architecture's calculated total (per 001's quickstart step 6) before nesting anything.

# 2. Nest the Application Component inside the VPC (FR-001).
curl -s "${AUTH[@]}" -X PATCH "$BASE/collections/$APP_ID" \
  -H 'Content-Type: application/json' \
  -d "{\"parent_collection_id\": \"$VPC_ID\"}" | jq
# Expect: 200, parent_collection_id == $VPC_ID

# 3. Recalculate and confirm the total is unchanged from before nesting (FR-009, SC-003).
curl -s "${AUTH[@]}" -X POST "$BASE/architectures/$ARCH_ID/calculate" | jq .total_price

# 4. Create a second VPC and move the Application Component into it (FR-002).
VPC2_ID=...      # from POST /architectures/$ARCH_ID/collections {"type":"vpc", ...}
curl -s "${AUTH[@]}" -X PATCH "$BASE/collections/$APP_ID" \
  -H 'Content-Type: application/json' \
  -d "{\"parent_collection_id\": \"$VPC2_ID\"}" | jq
# Expect: 200, parent_collection_id == $VPC2_ID (moved, not duplicated)

# 5. Un-nest it back to top-level (FR-003).
curl -s "${AUTH[@]}" -X PATCH "$BASE/collections/$APP_ID" \
  -H 'Content-Type: application/json' \
  -d '{"parent_collection_id": null}' | jq
# Expect: 200, parent_collection_id == null

# 6. Reject nesting a VPC inside a VPC (FR-004).
curl -s -o /dev/null -w '%{http_code}\n' "${AUTH[@]}" -X PATCH "$BASE/collections/$VPC_ID" \
  -H 'Content-Type: application/json' \
  -d "{\"parent_collection_id\": \"$VPC2_ID\"}"
# Expect: 400

# 7. Nest it again, then delete the VPC, and confirm the Application Component survives,
#    un-nested (FR-007, SC-004).
curl -s "${AUTH[@]}" -X PATCH "$BASE/collections/$APP_ID" \
  -H 'Content-Type: application/json' -d "{\"parent_collection_id\": \"$VPC2_ID\"}" > /dev/null
curl -s -o /dev/null -w '%{http_code}\n' "${AUTH[@]}" -X DELETE "$BASE/collections/$VPC2_ID"
# Expect: 204
curl -s "${AUTH[@]}" "$BASE/architectures/$ARCH_ID" | jq '.collections[] | select(.id=="'"$APP_ID"'")'
# Expect: the Application Component is present, parent_collection_id == null, its
# sku_selections unchanged from step 1.
```

**Expected outcome**: every step above matches, proving nest/move/un-nest all work, price is
unaffected by nesting alone, VPC-in-VPC is rejected, and deleting a VPC un-nests (never deletes)
its children.

## Frontend smoke check

With both servers running, open the Create Architecture page for an Architecture with a VPC and
an Application Component. Drag the Application Component onto the VPC and confirm it renders
nested inside. Drag it onto a different VPC and confirm it moves. Drag it out onto open canvas
and confirm it returns to top-level. Delete the VPC while it contains a nested component and
confirm the component reappears at top-level rather than disappearing.
