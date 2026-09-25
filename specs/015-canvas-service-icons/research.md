# Phase 0 Research: Canvas Service Icons & Per-Architecture Pricing Results

All Technical Context unknowns are resolved below. Findings come from the live codebase, the
real AWS pricing Parquet snapshot (`DATA/pricing_aws/parquet`, 250 distinct service codes), and
the AWS icon package (`images-web/aws_architecture_icons`, release `07312026`).

---

## 1. Where does the service → icon mapping live, and how is it produced?

**Decision**: A one-off, re-runnable generator script
(`backend/scripts/generate_aws_service_icon_map.py`) does the approximate matching and writes
two checked-in outputs:

1. `frontend/src/lib/awsServiceIcons.generated.ts`: a plain `Record<string, string>` from
   service code to icon file name, plus a `(service_code, product_family)` override table.
2. `frontend/src/assets/aws-icons/*.svg`: copies of **only** the icons the map references,
   plus the fallback and data-transfer icons (see §4).

A hand-written `frontend/src/lib/awsServiceIcons.ts` exposes `resolveAwsServiceIcon(serviceCode,
productFamily)`, which returns an icon URL. It uses Vite's `import.meta.glob` over
`assets/aws-icons/*.svg` with `?url`, so each icon is a separate hashed asset loaded on demand
rather than inlined into the JS bundle.

**Matching algorithm (in the script)**:
- Normalize both sides: lowercase, strip a leading `amazon`/`aws`, and drop all
  non-alphanumerics. For icons, use the file stem between `Arch_` and `_48`.
- Try an exact normalized match on the service code, then on `service_dim.service_name`, then
  a `difflib` close match (cutoff 0.8) on the service name.
- A checked-in `OVERRIDES` dict in the script corrects wrong fuzzy hits and fills misses. The
  override always wins over the automatic match.
- The script prints a report with three sections: matched, overridden, and unmatched (fallback).
  That report is how a person reviews the mapping (FR-003: "deterministic and reviewable").

**Prototype results** (run during this research): 170 of 250 service codes matched automatically.
Some fuzzy hits were wrong and need overrides, for example `AWSOutposts → Amazon-S3-on-Outposts`
should be `AWS-Outposts-family`. Obvious overrides that lift coverage above 90% (SC-002):
`AmazonEKS → Amazon-Elastic-Kubernetes-Service`, `AmazonDocDB → Amazon-DocumentDB`,
`ElasticMapReduce → Amazon-EMR`, `AmazonKinesisFirehose → Amazon-Data-Firehose`,
`AmazonKinesisAnalytics → Amazon-Managed-Service-for-Apache-Flink`,
`AmazonGlacier`/`AmazonS3GlacierDeepArchive → Amazon-Simple-Storage-Service-Glacier`,
`AmazonMCS → Amazon-Keyspaces`, `AmazonDAX → Amazon-DynamoDB`,
`AmazonQuickSight`/`AmazonQuickSuite → Amazon-Quick`, `AWSIoT → AWS-IoT-Core`,
`AWSEvents → Amazon-EventBridge`, `AWSFIS → AWS-Fault-Injection-Service`,
`AmazonGameLift → Amazon-GameLift-Servers`, `AmazonOmics → AWS-HealthOmics`,
`AuroraDSQL → Amazon-Aurora`, `AmazonAppStream → Amazon-WorkSpaces`,
`AmazonWorkSpaces* → Amazon-WorkSpaces`, `AmazonChime* → Amazon-Chime`,
`AmazonConnect*`/`ContactLensAmazonConnect`/`CustomerProfiles` → `Amazon-Connect`,
`AmazonBedrock*`/`AmazonKnowledgeBase → Amazon-Bedrock`,
`AWSStorageGatewayDeepArchive → AWS-Storage-Gateway`,
`IngestionServiceSnowball`/`SnowballExtraDays → AWS-Snowball`,
`AmazonEC2OCPULicenseFees → Amazon-EC2`, `AmazonRDSOCPULicenseFees → Amazon-RDS`,
`AmazonEVSLicensesIncluded → Amazon-Elastic-VMware-Service`,
`AWSIAMAccessAnalyzer → AWS-Identity-and-Access-Management`,
`AmazonLightsail → Amazon-Lightsail-for-Research`.
Retired or unmatched services (e.g. `A4B`, `AmazonHoneycode`, `AmazonSumerian`, `nimble`) stay
on the fallback.

**Product-family overrides** (the `(service_code, product_family)` table, checked before the
service-code map):
- `AmazonEC2` + `Storage`, `Storage Snapshot`, `EBS direct API Requests`,
  `Fast Snapshot Restore`, `ProvisionedRateVolumeInitialization` → `Amazon-Elastic-Block-Store`
- `AmazonEC2` + `NAT Gateway` → `Amazon-Virtual-Private-Cloud`
- `AmazonEC2` + `Load Balancer`, `Load Balancer-Network`, `Load Balancer-Application` →
  `Elastic-Load-Balancing`
- `AmazonVPC` + `VpcEndpoint` → `AWS-PrivateLink`
- `AmazonRDS` + `Aurora Global Database` → `Amazon-Aurora`

**Rationale**: The mapping is presentation data, which is Principle VI's simplest home, so it
belongs in the frontend and needs no API or database. Generating it from the real data meets the
user's instruction to "analyze the different service codes available in parquet and do approximate
matching". Checking in the output (not generating at build time) keeps builds and CI independent
of the local icon package and Parquet path, and makes every mapping change visible in code review.
Copying only the referenced SVGs (about 180 files, roughly 0.6 MB total, loaded on demand) avoids
shipping the full ~1 MB, 305-icon set.

**Alternatives considered**:
- *Runtime fuzzy matching in the browser*: rejected. It isn't reviewable, results can change
  whenever the icon set changes, and it would ship all 305 icons.
- *Backend endpoint that returns icon names*: rejected. It adds an API surface for pure
  presentation, and the icons would still need serving from the frontend.
- *PNG instead of SVG*: rejected. SVG stays crisp at every canvas zoom level (FR-013). The spec's
  "48" refers to the icon-package size variant, and the SVGs used are the ones in its `48/`
  folders.

## 2. Is product family available to the canvas?

**Finding**: No. `SKUSelectionOut` carries `service_code`, `sku`, `unit` and `attributes`, but not
`product_family`. Checked against the real data, `attributes_json` does not contain the product
family either, although `usagetype` and `operation` **are** present, lower-cased
(e.g. `"usagetype": "USE1-TimedPITRStorage-ByteHrs"`, `"operation": ""`).

**Decision**: Add `product_family: str | None = None` to `SKUSelectionOut`. It is resolved at
response time from `product_dim.product_family` in the same batched DuckDB lookup that already
resolves `attributes`, and is never stored in Postgres. In `catalog.py`, a new
`resolve_product_details(skus, region)` selects `service_code, sku, attributes_json,
product_family` with the existing region-scoping `WHERE` clause and returns
`{(service_code, sku): ProductDetails(attributes, product_family)}`. `resolve_attributes` becomes a
thin wrapper around it, so its other callers are unaffected. `architecture_service`'s
`_region_grouped_batch_resolve` and `sku_selection_out_with_unit` switch to the combined lookup,
so there is still one attributes query per distinct region, not two. An empty string
`product_family` (which exists in the data) is normalized to `None`.

**Rationale**: Principle II keeps vendor attributes out of Postgres, and principle IV means the
field goes through Pydantic and the generated TypeScript types. Using the same batch query keeps
existing performance (Principle VI).

**Alternatives considered**: separate `resolve_product_families` query (rejected: doubles
DuckDB round trips per region for no benefit); icon choice by service code only (rejected:
EC2's EBS/NAT/ELB rows would all show the EC2 icon; the user explicitly allowed "service code
and/or product family").

## 3. Pop-up content: which attribute keys, and in what order?

**Decision**: A pure function, `buildServicePopupLines(selection)` in
`frontend/src/lib/servicePopup.ts`, returns an ordered `string[]`:
1. `service_code`
2. `Sku: ${sku}`. This is always the real SKU, including for data transfer.
3. For data transfer only, the existing `awsDataTransferLabel(...)` region-pair label (FR-010).
4. `summarizeAttributes(attributes)`, the existing identifying-detail summary (clarification Q3).
   Omitted when it is empty.
5. `UsageType: ${attributes.usagetype}`, omitted when missing or empty.
6. `Operation: ${attributes.operation}`, omitted when missing or empty (it is often `""` in the
   data, as for DynamoDB PITR above).

The icon's `aria-label` is the same lines joined with `", "` (FR-012).

**Rationale**: One pure function drives the pop-up, the accessible name and the unit tests. It
reuses the existing `skuDetail.ts` and `awsDataTransfer.ts` helpers, which keeps it DRY.

## 4. Fallback and data-transfer icons

**Finding**: The service-icon set has no general "unknown service" icon and no icon for
`AWSDataTransfer`. Data transfer appears in a seeded standard architecture inside a box
(`architectures[0].collections[0].sku_selections[9]`), so SC-002 requires it to show a real icon.

**Decision**:
- **Fallback**: the group icon `Architecture-Group-Icons_07312026/AWS-Cloud-logo_32.svg`, with its
  `_Dark` variant under the `.dark` theme. It's a neutral AWS mark that reads clearly as "an AWS
  service".
- **AWSDataTransfer**: the General resource icon `Res_Data-Stream_48_{Light,Dark}.svg`. This is
  the single documented exception to "service icons only". The spec's Assumptions will be updated
  to name it.
- Theme-aware icons render both `<img>` variants, toggled with Tailwind `dark:hidden` /
  `hidden dark:block`, which matches the existing `.dark` custom variant in `index.css`.

**Alternatives considered**: a lucide `Cloud` glyph as the fallback (rejected: it isn't an AWS
icon, and the spec says to use the official set); reusing `AWS-Data-Transfer-Terminal` for data
transfer (rejected: it's a different product and would mislead).

## 5. How do icons and pop-ups scale with zoom?

**Findings**:
- Service rows render inside React Flow node components, and the whole viewport is one CSS
  transform (`scale(zoom)`). Anything rendered **inside the node** already scales with the zoom
  buttons, scroll-zoom and `fitView`, exactly as today's text does. The same is true in the
  pop-out canvas, which is a second `ArchitectureDiagramPanel` instance.
- Node height is **measured** from the DOM (`useMeasuredHeight`), not estimated from text, so
  swapping the text list for a wrapping row of icons needs no layout-math changes.
- The existing shadcn/Radix `Tooltip` portals its content to `document.body`. That puts the
  pop-up outside the transformed viewport, so it would **not** scale.

**Decision**:
- Icons render inside the node as a `flex flex-wrap gap-1` row of fixed CSS size (24 × 24 px at
  raw zoom 1, about 2× the `text-2xs` line height). They scale through the viewport transform with
  no extra code (FR-013).
- The pop-up keeps using the existing `Tooltip` (portal, collision handling, focus and hover
  behavior, and escaping the node's bounds and stacking order). Its content wrapper sets
  `fontSize: calc(var(--text-2xs) * zoom)`, with padding and line gap in `em`, where `zoom` is the
  live React Flow zoom (`useViewport().zoom` / `useStore(s => s.transform[2])`, already used in
  this component for the zoom readout). Because the real layout size changes rather than a CSS
  `transform: scale`, floating-ui positioning and collision detection stay correct (FR-014).

**Alternatives considered**: rendering the pop-up inside the node without a portal (rejected: it
gets clipped by the node box and sits under sibling nodes); applying `transform: scale(zoom)` to
the tooltip content (rejected: floating-ui measures the unscaled box, which breaks placement and
collision flipping).

## 6. Per-architecture pricing results: storage, keys, and races

**Findings**:
- `WorkspacePage.tsx` holds a single `calculation` state that is never keyed by architecture,
  which is the bug.
- `lib/priorCalculation.ts` already persists a per-architecture price-change **baseline** in
  `localStorage` (`cloud-pricing-prior-calculation-<architectureId>`), with try/catch and a type
  guard. That is the pattern clarification Q1 chose.
- The `calculate` mutation's `onSuccess` reads the active `architectureId`,
  `currentPriceChangeSelections` and `priorCalculation` from the closure. A result that arrives
  after a switch would therefore be compared against the **wrong** architecture's baseline.

**Decision**:
- New `frontend/src/lib/architecturePricingResults.ts` with
  `readPricingResult(architectureId)`, `writePricingResult(architectureId, entry)` and
  `removePricingResult(architectureId)`. It follows the same `localStorage` + try/catch + type-guard
  pattern, under the key `cloud-pricing-result-<architectureId>` (entry shape in data-model.md).
  A corrupted or old-shape entry reads as `null`, which triggers auto-calculation (edge case).
- `WorkspacePage` keeps an in-memory `Map<architectureId, PricingResultEntry>`, hydrated from
  storage on first access, and a separate in-memory `Map<architectureId, string>` for errors (FR-021:
  errors are per-architecture and not persisted).
- The mutation's **variables** capture the full request context at call time: `{ architectureId,
  duration, pricedContents, prior }`. `onSuccess` and `onError` use only the variables, never the
  closure, so a late result is stored against the architecture it was requested for (FR-020). The
  price-change decision uses the captured `prior` and `pricedContents`, and then writes both that
  architecture's baseline and its result entry. The active view reads `entries.get(activeId)`, so
  a result for another architecture can never render (FR-016).
- Auto-calculation (FR-017) runs from a `useEffect` on `[architectureId, architectureLoaded]`. It
  fires when the architecture's data has loaded, it has at least one SKU selection, there is no
  stored entry, and no request for that architecture is already in flight. The in-flight set is
  tracked per architecture so rapid switching doesn't double-fire.
- Duration (FR-018b): on switch, if an entry exists, `setCalculationDuration(entry.duration)`.
  Otherwise the current value is kept and used for the auto-calculation.
- Deletion: `deleteArchitecture.onSuccess` calls `removePricingResult(id)` and clears the
  in-memory entries.

**Rationale**: This reuses an established, tested pattern. It needs no backend or schema change
and satisfies Principle II, since derived prices never reach Postgres. Capturing context in
mutation variables is the standard TanStack Query way to make `onSuccess` correct across renders.

**Alternatives considered**: TanStack Query cache keyed by `["calculation", architectureId]`
(rejected: `calculate` is a user-triggered mutation with price-change side effects, not
idempotent cached data, and cache GC/persistence would need a new persister dependency);
`sessionStorage` (rejected by clarification Q1).

## 7. "Out of date" detection (FR-018a)

**Decision**: A result entry stores `pricedContents: PricedContentsEntry[]`. This is the existing
`PriceChangeSelection` shape (service_code, sku, pricing_term, purchase_option, usage_quantity)
**plus `region`**, because a service's price also depends on the region of the Collection that
owns it. A new pure `pricedContentsEqual(a, b)` in `priceChange.ts` reuses the same
order-independent multiset comparison as `selectionsEqual`, generalized over a key function.
Staleness is `!pricedContentsEqual(entry.pricedContents, currentPricedContents)`, computed on every
render from the live architecture query data. That makes "changed back to what was priced clears
the notice" automatic. Duration is not part of the comparison, per the spec assumption.

**Rationale**: It is pure and trivially unit-testable, reuses the existing comparison semantics,
and needs no server round trip.

## 8. Word-wrap toggle relocation (FR-023)

**Finding**: `PricingPanel.tsx` renders the toggle after the Data Timestamp line, and the
"Price per Sku" heading lives inside `PricePerSkuSection`.

**Decision**: Pass `wordWrap` / `onToggleWordWrap` into `PricePerSkuSection` and render its
heading as `flex items-center justify-between`. The heading text sits on the left and the existing
tooltip button on the right (`shrink-0`). The button's right edge lines up with the price column,
because both are right-aligned within the same section width. The heading text gets
`min-w-0 truncate` so a narrowed column never overlaps the button. The out-of-date notice
(FR-018a) renders directly under the Data Timestamp line, which becomes the column's last element.

## 9. Testing approach

- **Backend (test-first, Principle V; DuckDB query logic)**: unit test for
  `resolve_product_details` against the Parquet fixture, covering present and empty
  product_family and the data-transfer `fromRegionCode` scoping. Contract test asserting
  `product_family` on architecture detail and on single SKU-selection responses. The fixture may
  need a `product_family` value added through `build_test_pricing_fixture.py`.
- **Frontend unit (Vitest, test-first for pure logic)**: `awsServiceIcons` (product-family
  override wins, service-code match, fallback, determinism), `servicePopup` (the DynamoDB example
  from the spec verbatim, omitted lines, data-transfer line), `architecturePricingResults`
  (round-trip, corrupt entry → null, remove), `pricedContentsEqual` (order-independence, region
  sensitivity), and the auto-calculate decision helper.
- **Frontend component tests (Testing Library)**: the icon list renders an `img` per selection
  with an accessible name, and the tooltip content shows on focus. `PricingPanel` places the
  word-wrap toggle on the heading row and shows the out-of-date notice below Data Timestamp.
- **Manual/visual**: zoom scaling, pop-out canvas, and the architecture-switch flows in
  quickstart.md.
