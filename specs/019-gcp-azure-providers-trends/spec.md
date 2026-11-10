# Feature Specification: GCP and Azure Providers, Trends Page, Saved Preferences and Diagram Arrows

**Feature Branch**: `019-gcp-azure-providers-trends`

**Created**: 2026-11-02

**Status**: Draft

**Input**: User description: "../speckit-inputs/cloud-pricing-app-new-providers-new-pages.md". In summary: (1) turn on the GCP and Azure provider buttons, with the same architecture building and service search as AWS, customized per provider; (2) a first Trends page with charts of price movement and highest and lowest price lists; (3) keep user preferences on the server instead of only in the browser; (4) arrows on the architecture diagram; (5) LLM agent integrations as future state only.

## Clarifications

### Session 2026-11-02

- Q: Which Trends metrics are in the first version? → A: Price Trend, Cumulative Change and Share of SKUs Changed, each with a category filter. Revised on 2026-11-03; see the next session.
- Q: Which browser-only settings move to the server? → A: General settings only: Trends selections, column widths, collapsed columns and last selected provider. Settings tied to one architecture stay in the browser (FR-023).
- Q: What do one-to-many and many-to-one arrows mean? → A: A connector that branches from one box to several, or joins several into one. Any data transfer selection on it is priced once, with no extra pricing logic. This can move to a future release if it adds too much complexity (FR-027, FR-027a).
- Q: When several regions are selected for one provider on the Trends chart, is it one line per region or one combined line? → A: One combined series per provider, covering all of its selected regions. To see a single region on its own, the user selects only that region (FR-012).
- Q: Should GCP and Azure search cover the whole catalog or only core services? → A: The whole catalog. Every SKU can be priced with common fields. VMs, block storage, object storage, data transfer out and managed databases get tuned fields and are tested against the reference lookups (FR-004, FR-005, FR-005a).
- Q: What should the right-hand side of the Trends page show? → A: Biggest movers, which replaces the highest and lowest price lists: the 3 largest % price increases and 3 largest decreases over a selected period, per provider, category and regions. A % change has no unit, so it compares fairly across services (FR-016 to FR-019).

### Session 2026-11-03

- Q: How are tiered prices applied, and for which providers? → A: Graduated tiers for AWS, Azure and GCP alike. The usage quantity is split across the tiers and each part is priced at its own tier's rate. For example, with tiers 0–10, 10–20 and 20–1000, a quantity of 40 is priced as 10 at tier 1, 10 at tier 2 and 20 at tier 3. Tiers apply per line, not pooled across lines. Free allowances apply only when the provider publishes them as a tier. This also fixes AWS, which today uses a single, arbitrary tier (FR-008).
- Q: Which Trends chart metrics are in the first version, given how rarely list prices change? → A: Only **SKUs Changed**: per week, the number of compared SKUs whose price went up and the number that went down. Price Trend and Cumulative Change are dropped. Real AWS data showed about 1 price change among about 122,000 compared SKUs over 3 weeks, so any median change is 0% (FR-011, FR-012, FR-015).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Build and price a GCP or Azure architecture (Priority: P1)

A user picks GCP or Azure in column 1 and works exactly as they do with AWS today. They create an architecture, find services in column 2, set up a selection in the Service Editor in column 3, place it on the diagram, and calculate prices. Search and the editor fields fit the provider's own catalog, for example Azure price types or GCP commitment options. The overall flow, layout and controls stay the same.

**Why this priority**: The GCP and Azure pricing data is already being collected. Turning it on is the largest gain in value and the base for comparing providers on the Trends page.

**Independent Test**: Select Azure, create an architecture, add a Linux VM in one region, a managed disk and outbound data transfer, then calculate. Do the same for GCP. Each price must match the provider's published price for that snapshot.

**Acceptance Scenarios**:

1. **Given** the GCP and Azure pricing data has a usable snapshot, **When** the user opens the workspace, **Then** the GCP and Azure buttons in column 1 are enabled alongside AWS.
2. **Given** Azure is selected, **When** the user searches for "virtual machines" in a region, **Then** column 2 lists matching Azure services and SKUs available in that region, including SKUs priced only globally.
3. **Given** a GCP SKU is selected, **When** the Service Editor opens, **Then** it shows the fields that apply to GCP (for example on-demand vs commitment options and usage quantity in the SKU's unit) and hides fields that only apply to AWS.
4. **Given** an Azure or GCP architecture with several selections, **When** the user calculates, **Then** the total and each line item come from that provider's current snapshot. The snapshot date is shown as it is for AWS.
5. **Given** a price the provider doesn't publish (stored as missing), **When** it would appear in a result, **Then** it shows as "unavailable", never as zero.
6. **Given** one provider's latest snapshot is failed, partial or stale, **When** the user works with another provider, **Then** that other provider works normally. The affected provider shows its own status message.

---

### User Story 2 - See how prices are moving on the Trends page (Priority: P2)

A user opens the Trends tab. On the left, they pick one or more providers and, under each provider, one or more regions, and optionally a category. The chart shows **SKUs Changed** over time: for each week, the number of SKUs whose price went up and the number whose price went down, compared with the week before. Each provider gets one up/down pair, combining all the regions selected for that provider.

**Why this priority**: It turns the weekly snapshots the app already receives into insight about how providers' prices move, which isn't possible today.

**Independent Test**: With at least three weekly snapshots for a provider, select that provider with two regions. The chart shows one up/down pair, each point the number of SKUs across both regions whose price rose or fell that week. The counts match a manual comparison of the snapshots.

**Acceptance Scenarios**:

1. **Given** the Trends tab is enabled, **When** the user opens it for the first time, **Then** it loads with defaults (all providers, all regions, all categories) and shows the chart.
2. **Given** the user selects AWS us-east-1 and Azure eastus, **When** the chart draws, **Then** it shows two up/down pairs, one per provider, each labeled with the provider and its selected regions.
3. **Given** a selection whose provider has fewer than two snapshots, **When** the chart draws, **Then** that selection shows a "not enough history yet" note instead of a line.
4. **Given** a point on the chart, **When** the user hovers it, **Then** they see the week, the number of SKUs up and down, those numbers as a % of the SKUs compared, how many were compared and how many were left out.
5. **Given** the Compute category is chosen, **When** the chart draws, **Then** only compute SKUs are counted.
6. **Given** a week in which no compared SKU changed price, **When** the chart draws, **Then** that week shows 0 up and 0 down. A week with no compared SKUs at all shows "no data".

---

### User Story 3 - See the biggest price movers per category (Priority: P2)

On the right of the Trends page, the user picks a provider, a category (all categories, compute, storage, database or networking), optionally one or more regions, and a period. The page lists the 3 SKUs whose price rose the most and the 3 whose price fell the most over that period, by % change.

**Why this priority**: It shows which prices are actually moving. A % change has no unit, so it compares fairly across services priced per hour, per GB or per request. It also starts the shared categories that later cross-provider comparison will need.

**Independent Test**: Select AWS, Compute, all regions and the last 13 weeks. The two lists each show up to 3 SKUs, each with service, SKU description, region, price at the start and end of the period, unit and % change. They match a manual comparison of the two snapshots.

**Acceptance Scenarios**:

1. **Given** a provider, category, regions and period are selected, **When** the lists load, **Then** "Largest increases" and "Largest decreases" each show up to 3 SKUs, ranked by % change, with service name, SKU description, region, start price, end price, unit and % change.
2. **Given** no regions are selected, **When** the lists load, **Then** they cover all of the provider's regions.
3. **Given** fewer than 3 SKUs changed price in that direction during the period, **When** the lists load, **Then** they show only what exists. When none changed, the list says "No price changes in this period".
4. **Given** the provider's history is shorter than the selected period, **When** the lists load, **Then** they use the history available and say which weeks were compared.

---

### User Story 4 - Selections and layout follow the user to any device (Priority: P3)

The user's Trends selections and other preferences are saved to their account on the server, not only in their browser. When they sign in on another browser or device, or after clearing browser data, the Trends page and workspace open the way they left them. A **Reset** button on each half of the Trends page goes back to the defaults.

**Why this priority**: The input explicitly asks for it, and it is needed so Trends selections persist. It also replaces several browser-only settings stores with one place that is easy to extend.

**Independent Test**: In browser A, choose Trends selections and change a column width. Sign in to browser B as the same user: the same selections and width appear. Press Reset: defaults return and stay after a reload.

**Acceptance Scenarios**:

1. **Given** the user changed Trends selections, **When** they return to the Trends page in a new session, **Then** the last selections are restored.
2. **Given** the user presses Reset on the charts section, **When** the page updates, **Then** chart selections return to defaults (all providers, all regions, all categories) and the default is what is saved. The lists section is not affected, and vice versa.
3. **Given** the user has preferences saved only in the browser from an earlier version, **When** they first load this version, **Then** those values are moved to their account once and keep working.
4. **Given** the server can't be reached when a preference is saved, **When** the user keeps working, **Then** the page keeps the change for the session and tries again; it never blocks the user.

---

### User Story 5 - Clearer diagrams with arrows (Priority: P3)

A user marks connectors on the architecture diagram as one-way arrows, two-way arrows, one-to-many (one box branching to several) or many-to-one (several boxes joining into one), to show how data or requests flow. A connector doesn't need a data transfer price to have an arrow.

**Why this priority**: It improves how readable a diagram is, but doesn't change any price.

**Independent Test**: Draw a connector between two collections, set it to one-way, then two-way, then one-to-many. The diagram shows the matching end markers, the style survives a reload, and the architecture's price doesn't change.

**Acceptance Scenarios**:

1. **Given** a connector, **When** the user picks an arrow style, **Then** the diagram shows that style at the correct ends.
2. **Given** a connector without a data transfer selection, **When** an arrow style is set, **Then** it is saved and shown, and nothing is added to the price.
3. **Given** a one-way connector, **When** the user reverses its direction, **Then** the arrow points the other way.
4. **Given** an architecture with arrow styles is exported and imported, **Then** the styles are kept.
5. **Given** a connector from box A to box B, **When** the user makes it one-to-many and adds box C, **Then** the diagram shows one connector from A branching to B and C.
6. **Given** a branching connector with a data transfer selection, **When** the user calculates, **Then** the data transfer is priced once, the same as on an ordinary connector.

---

### Edge Cases

- A provider has no usable snapshot yet: its button stays disabled with a short reason, and Trends leaves it out of the selection with a note.
- A GCP SKU covering several regions (multi-regional) appears in each member region. Trends and the lists count it once per region selected, never twice in one region.
- Global-only prices (for example support plans or licensing) are found when searching any region and shown as "global".
- Global-only prices in Trends and movers (Azure, GCP): they count once per provider, as their own location "global", whenever the selection covers all regions or at least one region of that provider. They are never counted once per selected region.
- A SKU appears in one week but not the next (new or removed): it is left out of that week's comparison, and the hover detail says how many were left out. A new SKU is not a price change, and a removed SKU is not a −100% change.
- A price is missing or zero in one of two weeks: the SKU is left out of that week's comparison, never counted as a change.
- A snapshot was re-published with a new revision for the same week: only the latest revision for each week is used.
- Prices published in a currency other than USD are already stored as missing. They show as "unavailable", never converted.
- Tiered prices (data transfer, storage): trends and movers compare the first non-zero tier, so a free first tier doesn't hide a change. That is stated in the hover detail and list.
- The same SKU changes price in several regions: each region is a separate entry in the movers lists, so one SKU can appear more than once.
- Guest users: preferences are saved against the guest identity and are lost when that identity is.
- A box on a branching connector is deleted: that branch is removed. If only two boxes are left, it becomes an ordinary connector. If one is left, the connector is removed.
- A branching connector's boxes are in different regions: allowed. Any data transfer selection is still priced once (FR-027a).
- A category filter leaves no SKUs in a selection for a week: that point is shown as "no data", not as 0.
- History is still being built (first start or a rebuild): the chart shows the weeks built so far with a "building history (n of m weeks)" note, and the movers lists say which weeks were compared.

## Requirements *(mandatory)*

### Functional Requirements

**Providers (GCP and Azure)**

- **FR-001**: The GCP and Azure buttons in column 1 MUST be enabled when that provider has a usable snapshot, and disabled with a reason otherwise.
- **FR-002**: Each provider's snapshot status (current, partial, failed, stale) MUST be read and shown independently. One provider's status MUST NOT affect another's.
- **FR-003**: Architecture creation, listing, rename, delete, sharing, collections, connectors and price calculation MUST work for GCP and Azure the same way they work for AWS. An architecture belongs to exactly one provider.
- **FR-004**: Service search in column 2 MUST search the selected provider's whole catalog by name, service and region, the same as AWS. It MUST include SKUs priced in the region and SKUs priced only globally.
- **FR-005**: The Service Editor in column 3 MUST let any SKU from the catalog be priced with common fields: price type, unit and usage quantity in the SKU's own unit. Fields that don't apply to the provider MUST be hidden. Price types available: on-demand for all three providers; Azure reservation and savings plan prices where published; GCP commitment prices where published.
- **FR-005a**: Five core kinds of services MUST get fields tuned to them: VMs, block storage, object storage, data transfer out and managed relational databases. For example, a GCP VM is priced from its vCPU and memory SKUs together. Each MUST be tested against that provider's reference lookups.
- **FR-006**: Requests the screens make MUST have the same shape and behavior for every provider. Only the provider value and provider-specific fields differ, so the screens don't need provider-specific request handling.
- **FR-007**: Prices MUST be shown exactly as published, in USD. Missing prices MUST be shown as "unavailable", never as zero or an estimate.
- **FR-008**: Tiered prices MUST be applied as graduated tiers for every provider (AWS, Azure and GCP): the usage quantity is split across the published tiers and each part is priced at its own tier's rate. Example: with tiers 0–10, 10–20 and 20–1000, a quantity of 40 is 10 at the tier 1 rate, 10 at the tier 2 rate and 20 at the tier 3 rate. Tiers apply to each line on its own, not to usage pooled across lines. A free allowance applies only when the provider publishes it as a tier. If a quantity goes past the highest published tier's upper bound, the excess MUST be priced at the rate of the tier with the highest upper bound. The line item MUST show the tier breakdown.
- **FR-009**: The Admin tab's snapshot status MUST show each provider separately.

**Trends charts**

- **FR-010**: The Trends tab MUST be enabled and open a Trends page with a charts section and a biggest-movers lists section.
- **FR-011**: The charts section MUST let the user select one or more providers and, under each, one or more regions, plus one category (FR-015a).
- **FR-012**: The chart MUST show **SKUs Changed**: for each pair of consecutive weekly snapshots, the number of compared SKUs whose on-demand unit price went up and the number that went down. A SKU's change is (current price − previous price) ÷ previous price. It is drawn as one up/down pair per provider over time, each combining the SKUs of all the regions selected for that provider. The hover MUST also show each number as a % of the SKUs compared.
- **FR-013**: Only SKUs with a valid, non-zero price in both weeks MUST be compared. The number compared and the number left out MUST be available on hover.
- **FR-014**: The chart MUST use every weekly snapshot available for that provider, up to the last 52 weeks.
- **FR-015**: Price Trend (median weekly % change) and Cumulative Change are not in this version. List prices change too rarely for a median to move (see Assumptions, "Trends signal"). They may return in a later version if real history shows they would be useful.
- **FR-015a**: The chart MUST have a category filter (all categories, compute, storage, database, networking), using the same categories as the movers lists (FR-017). Only SKUs in the chosen category are included.

**Biggest movers lists**

- **FR-016**: The movers section MUST let the user select one provider, one category (all categories, compute, storage, database or networking), zero or more regions (zero meaning all regions) and a period: the last 1, 4, 13 or 52 weeks. The default is 52 weeks, because list prices change rarely.
- **FR-017**: The system MUST group each provider's services into at least these shared categories: compute, storage, database and networking. Services that fit none are uncategorized: they are included only under "all categories", in both the chart and the movers lists, and never under a named category.
- **FR-018**: For the selection, the system MUST compare each SKU's on-demand price in the latest snapshot with its price at the start of the period. It MUST show the 3 largest % increases and the 3 largest % decreases. Only SKUs with a valid, non-zero price at both ends are compared. Ties are ranked by the size of the price change, then by name.
- **FR-019**: Each list entry MUST show service name, SKU description, region, start price, end price, unit and % change, all exactly as published.

**Preferences**

- **FR-020**: Both Trends sections MUST have a Reset button that restores that section's defaults. Charts: all providers, all regions, all categories. Movers: the first available provider, all categories, all regions, 52 weeks. Each Reset affects only its own section.
- **FR-021**: The last Trends selections MUST be saved to the user's account and restored in later sessions, on any browser or device.
- **FR-022**: User preferences MUST be stored on the server per user, in one extensible record, so that new preferences can be added without changing how they are stored.
- **FR-023**: These general settings MUST move to the user's account in this feature: Trends selections, column widths, collapsed columns and last selected provider. Settings that belong to one architecture (box positions, connector bends and sides, zoom and pan, icon layout, last calculation) stay in the browser for now.
- **FR-024**: Preferences found in the browser from earlier versions MUST be moved to the account once on first load. After that, the server copy is used.
- **FR-025**: Failing to save a preference MUST NOT block the user or show a blocking error. The change applies for the session and is retried.

**Diagram arrows**

- **FR-026**: Each connector MUST have an arrow style: none (the default, today's appearance), one-way, two-way, one-to-many or many-to-one.
- **FR-027**: A one-to-many connector MUST start at one box and branch out to two or more boxes. A many-to-one connector MUST join two or more boxes into one. The user MUST be able to add a box to, or remove a box from, a branching connector. Removing branches until only two boxes remain turns it back into an ordinary connector.
- **FR-027a**: A data transfer selection on a branching connector MUST be priced once for the connector, exactly as it is on an ordinary connector. Branches add no pricing logic.
- **FR-028**: The user MUST be able to reverse a directional connector.
- **FR-029**: Arrow styles MUST be saved with the architecture and kept by export/import and copying. They MUST NOT change any price.
- **FR-030**: Connectors MUST be allowed without a data transfer selection.

**Out of scope**

- **FR-031**: Comparing prices across providers (for example, matching EC2 to Azure VMs to Compute Engine) and LLM agent integrations (questions on prices, building diagrams from descriptions, MCP) are out of scope. They are recorded as future state only.

### Key Entities

- **Provider**: AWS, GCP or Azure. Has its own catalog, latest snapshot and snapshot status. Whether it can be selected depends on that status.
- **Provider snapshot**: One provider's pricing for one week, with a date and revision. Trends use a series of these.
- **Location**: A region, a multi-region location or "global". Prices for a region also include global prices.
- **Service category**: A shared grouping (compute, storage, database, networking) that each provider's services are mapped into.
- **Price mover**: One SKU in one region whose price changed over the selected period, with its start and end prices and % change.
- **Trend point**: For one provider (across its selected regions) and one week: the number of SKUs whose price went up, the number that went down, the number compared and the number left out.
- **User preferences**: One extensible record per user holding saved settings, such as Trends selections and workspace layout.
- **Connector arrow style**: The style and direction of one connector on one architecture. A branching connector (one-to-many or many-to-one) links one box to two or more others.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can build and price a three-item architecture (VM, disk, data transfer) in GCP and in Azure in under 5 minutes each, with the same steps as for AWS.
- **SC-002**: For the reference lookups (VM, block storage, object storage, data transfer out and managed database per provider), 100% of the prices shown match the provider's published price for the snapshot used.
- **SC-003**: No price is ever shown as zero or estimated when the provider doesn't publish it (0 cases in testing).
- **SC-004**: The Trends page shows the chart and both movers lists within 3 seconds of opening, for the default selection.
- **SC-004a**: Every movers entry matches a manual comparison of the two snapshots it is based on (prices exact, % change to 0.01 percentage points).
- **SC-005**: Every chart point's up, down, compared and left-out counts exactly match a manual comparison of the two snapshots, with and without a category filter.
- **SC-006**: In 100% of tests, a user's Trends selections and other saved preferences come back after signing in on a second browser.
- **SC-007**: A user can set or change a connector's arrow style in 2 clicks or fewer, and it survives reload, export and import 100% of the time.
- **SC-008**: When one provider's snapshot is unavailable, the other providers' workspaces and Trends lines keep working (verified per provider).

## Assumptions

- **Constitution**: Amended to v1.1.0 on 2026-11-02. GCP and Azure are in scope, and shared request shapes with per-provider handling are required (Principle III, "Multi-Provider by Design").
- **Trends signal**: Measured on AWS us-west-2 snapshots from 2026-09-15 to 2026-10-05: about 1 price change among about 122,000 compared SKUs, while 18 to 2,826 SKUs were added or removed per snapshot. A median of weekly changes is therefore 0%, which is why the chart counts changed SKUs instead (FR-012, FR-015). Azure and GCP are not measured yet.
- **Tiers**: Tiers are applied per line. Real bills pool usage across an account before applying tiers; pooling may come in a later feature. Fixing AWS tiers can change the totals of existing AWS architectures that use tiered prices (mostly data transfer); the new totals are the correct ones.
- **Pricing data**: GCP and Azure data comes from the upstream pipeline in the provider-specific tables and locations its notes describe. The app reads them as they are and never writes or changes pricing data.
- **History**: Snapshots are weekly per provider. The app can read older snapshots, not only the ones it currently caches. GCP and Azure history starts at their first snapshot (around 2026-10-31), so their trend lines start short.
- **Starter templates**: Existing starter templates stay AWS-only. GCP and Azure templates are not part of this feature.
- **Categories**: Categories are mapped from each provider's own service family or taxonomy. This mapping is a first version and will grow.
- **Currency**: All prices are USD. There is no currency conversion.
- **Comparisons**: Trends use on-demand prices only. Commitment and reservation prices are not part of trends in this version.
- **Preferences**: Preferences are per user, and guest identities get their own. Preferences are not shared between users.
- **Branching connectors**: These are mainly for flows within one region with no cost attached. If the plan finds that branching connectors (FR-027, FR-027a) add too much complexity, they can move to a future release. One-way, two-way and reverse direction (FR-026, FR-028 to FR-030) still ship in this feature.
