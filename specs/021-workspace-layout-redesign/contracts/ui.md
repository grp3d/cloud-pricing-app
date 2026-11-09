# UI Contract: Accessible Names and Roles (021)

The unit tests (Testing Library) and e2e tests (Playwright) find controls by role and
accessible name. This is the list they rely on.

- **Kept** means unchanged from today, so existing tests keep passing (FR-033).
- **New** means introduced by 021.
- **Removed** means the control no longer exists.

## Header (every page)

| Control | Role | Accessible name | Status |
|---|---|---|---|
| Workspace link | link | `Cloud Pricing` | Kept |
| Menu opener | button (`aria-haspopup="dialog"`, `aria-expanded`) | `Open architecture menu` | New |
| Current architecture label | (text, with tooltip) | `<Provider> · <name>`, e.g. `GCP · Web App` | New |
| Trends, Admin links | link | `Trends`, `Admin` | Kept |

## Architecture menu (Popover: role `dialog`, name `Architectures`)

| Control | Role | Accessible name | Status |
|---|---|---|---|
| Provider group | group (heading) | `AWS architectures`, `GCP architectures`, `Azure architectures` | New |
| Architecture row | button (`aria-current="page"` when open) | `<name>` | Kept (was in Column 1) |
| Public toggle | button | `Make <name> public` / `Make <name> private` | Kept |
| Delete | button | `Delete <name>` | Kept (opens the existing confirm dialog) |
| New, per group | button | `New AWS architecture…` (and GCP, Azure) | New (replaces `New Architecture`) |
| Name field, per group | textbox | `New AWS architecture name` (and GCP, Azure) | New (replaces `New Architecture name`) |
| Create, per group | button | `Create` | Kept text; one per open name field |
| Import, per group | button | Exactly `Import an AWS architecture`, `Import a GCP architecture`, `Import an Azure architecture` | New (replaces `Import an architecture`) |

**Removed**: the `Cloud providers` list and the `Architectures` Column 1 list region (the
menu's dialog takes the `Architectures` name). Also removed: `Resize provider/Architecture
panel`.

## Workspace zones

| Control | Role | Accessible name | Status |
|---|---|---|---|
| Left sidebar | complementary | `Architecture Editor` | New landmark name |
| Sidebar resize handle | separator | `Resize Architecture Editor panel` | Kept |
| Sidebar collapse | button | `Collapse panel` / `Expand panel` | Kept |
| Canvas pop-out | button | `Open the architecture canvas in an enlarged view` | Kept |
| Inspector | complementary | `Inspector` | New |
| Inspector resize handle | separator | `Resize inspector` | New (replaces `Resize pricing panel`) |
| Inspector collapse | button | `Collapse inspector` / `Expand inspector` | New |

**Removed**: `Resize Service Editor panel`.

## Inspector

| Control | Role | Accessible name | Status |
|---|---|---|---|
| Tab list (each pane) | tablist | `Inspector tabs` (merged) / `Upper inspector pane`, `Lower inspector pane` (split) | New |
| Pricing tab | tab | `Pricing` | New |
| Service tab | tab | `Service` | New |
| Tab options | button | `Pricing tab options` / `Service tab options` | New |
| Options menu items | menuitem | `Move to lower half` (merged); `Merge`, `Swap` (split) | New |
| Split divider | separator (`aria-valuenow`, 20–80) | `Resize inspector panes` | New |
| Rail buttons (collapsed) | button | `Pricing`, `Service` | New |
| Rail new-result marker | (part of the rail Pricing button's name) | `Pricing — new result` | New |
| Service tab empty state | text | `Select a service on the canvas` | New |

**Kept inside the Pricing tab**: `Duration` (label), `Calculate`, `Calculation result`
(region), `Price per Sku`, `Price components`, `Price tiers`, the Price Change text, the
out-of-date notice, and the word-wrap toggle.

**Kept inside the Service tab**: `Save`, `Remove this service`, `vCPUs`, `Memory (GiB)`,
`Operating system`, `Usage quantity` / `Hours per day`, and every other existing editor
field.

## Behaviour the tests may rely on

- Only the visible tab's panel is shown, but the Service tab's form stays in the DOM (hidden)
  so unsaved input survives (data-model §4). Tests should therefore query
  `getByRole(..., { hidden: false })` / Playwright's default visible-only locators.
- `Calculate` is reachable only while the Pricing tab is visible. The e2e `calculate()`
  helper clicks the `Pricing` tab first when it isn't selected.
