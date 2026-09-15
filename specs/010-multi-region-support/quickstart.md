# Quickstart: Multi-Region Collections and Region-Grouped Pricing

Manual/live-verification guide for this feature's user stories (spec.md). Run against a local dev stack with the multi-region Parquet dataset in place (7 regions confirmed present at the latest snapshot per research.md §3: `ap-northeast-1, eu-west-1, eu-west-2, us-east-1, us-east-2, us-west-1, us-west-2`).

## Prerequisites

- Backend running with Alembic migrations applied (including this feature's `region` backfill migration — data-model.md).
- Frontend dev server running (`frontend/`), pointed at that backend.
- An existing Architecture with at least one pre-migration Collection, to verify backfill (US1/FR-016 scenario below).

## Scenario 1 — Region prompt on collection creation (User Story 1)

1. In column 2, click "+Add", choose type "VPC", enter a name, click "Add".
2. **Expect**: a region-selection dialog appears before the VPC is created, listing the 7 available regions from `GET /regions`.
3. Choose a region, confirm. **Expect**: the VPC is created and associated with that region (visible via its diagram label, Scenario 8).
4. Repeat for an unattached Application (no VPC selected in column 2). **Expect**: same prompt.
5. Open the prompt and cancel. **Expect**: no collection is created.

## Scenario 2 — Region locks once content exists (User Story 2)

1. Select the empty VPC from Scenario 1. **Expect**: its region is editable (e.g., via a region field/control that isn't disabled).
2. Attach any service to it (or to a nested Application, or nest an Application into it).
3. **Expect**: the region control becomes disabled; attempting `PATCH /collections/{id}/region` directly returns `409`.

## Scenario 3 — Region inheritance when adding an Application inside a selected VPC (clarified addition to User Story 1)

1. Select the region-locked VPC (or any VPC) in column 2.
2. Click "+Add", type "Application", name it, click "Add".
3. **Expect**: no region prompt appears; the new Application is created already nested in the selected VPC, with that VPC's region.

## Scenario 4 — Same-region nesting enforced (User Story 3)

1. Create a VPC in region A and an unattached Application in region B (via Scenario 1's flow, picking different regions).
2. Drag the Application onto the VPC on the diagram (column 4).
3. **Expect**: the drag is rejected — the Application does not become nested, and a visible message explains the region mismatch (research.md §8: no prior rejection UI existed, this feature adds the first one).
4. Create an Application in region A instead, drag it onto the same VPC. **Expect**: nesting succeeds.

## Scenario 5 — Service search scoped to selected collection's region (User Story 4)

1. Select a collection in region A, open the service/catalog search, search for any known service.
2. **Expect**: only region-A results (`GET /catalog/skus?region=A...`).
3. Select a collection in region B, repeat the same search. **Expect**: results change to region-B services.

## Scenario 6 — Connector service search and direction (User Story 5, 6)

1. Create two collections in different regions (X and Y).
2. Use "Add Connector", set X as "From" and Y as "To". **Expect**: the service catalog shown reflects region X.
3. On the diagram, **expect**: the connector renders with an arrow pointing toward Y.
4. Instead, create a connector by selecting collection X then collection Y directly in column 2 and triggering connect. **Expect**: same result — X is "from", arrow points to Y, catalog reflects region X.

## Scenario 7 — Region labels on diagram boxes (User Story 9)

1. View a VPC's box on the diagram. **Expect**: its region name in the bottom-right corner, always.
2. View an unnested Application's box. **Expect**: its region name in the bottom-right corner.
3. Nest that Application into its same-region VPC. **Expect**: the Application's region label disappears (the VPC's own label already shows it).

## Scenario 8 — Region-grouped, subtotaled pricing breakdown (User Story 7)

1. Build an architecture with priced services in two different regions.
2. Calculate pricing.
3. **Expect** in column 5: the existing `Total` unchanged at top; below it, one labeled section per region, each listing only that region's line items (still price-descending within the section) followed by a region subtotal; the `Data Timestamp` line still last.
4. Repeat with only one region in use. **Expect**: still rendered as a single labeled, subtotaled section (not silently reverting to the old flat list).

## Scenario 9 — Legacy collection backfill (User Story 1, FR-016)

1. Inspect a Collection created before this feature shipped (pre-migration).
2. **Expect**: it now has a `region` equal to the app's former single global pricing region, with no user action required, and behaves per Scenario 2 (editable if still empty, locked if it already has content).

## Scenario 10 — Label rename (User Story 8)

1. Open column 2's collection-type selector.
2. **Expect**: reads "Application", not "Application Component" (and any other prior "Application Component(s)" text in the UI reads "Application(s)").
