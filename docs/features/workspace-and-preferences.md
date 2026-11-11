# Workspace and preferences

The app has three pages, reached from the dark header: **Cloud Pricing** (the workspace),
**Trends**, and **Admin** (administrators only). The person icon in the header shows who you
are and lets you log in or change user (see [accounts and sharing](accounts-and-sharing.md)).

## Architecture menu

The chevron beside **Cloud Pricing** opens the architecture menu, on every page. Picking an
architecture from Trends or Admin goes to the workspace with it open.

- The menu opens with the providers collapsed: AWS, GCP and Azure, each with its architecture
  count. Hovering or clicking a provider shows its panel to the right: its architectures, **New
  <provider> architecture…** (a name field and confirm, inside the menu) and **Import**.
- Each architecture row has, in order: share (make public or private), **Rename**, and delete
  (with a confirmation). Rename turns the name into a text field; Enter or leaving the field
  saves a changed name, Escape cancels, and a blank or unchanged name saves nothing.
- Import in a provider's panel lists only that provider's public architectures (see
  [accounts and sharing](accounts-and-sharing.md#importing-a-copy)).
- Picking an architecture opens it and switches the workspace to its provider. Its provider and
  name are shown in a title row above the canvas.
- The menu works from the keyboard: Enter, Space or ArrowRight on a provider opens its panel,
  ArrowLeft returns to the provider, Escape closes the menu and returns focus to the chevron.

## Layout

The workspace has three zones under the header:

- **Left sidebar, the Architecture Editor**: collections, connectors and the service search.
- **Center canvas**: the architecture diagram. It takes all the space the other two don't.
- **Right inspector**: two tabs, **Pricing** and **Service**.

The sidebar and the inspector can each be resized by dragging their inner edge, and collapsed to
a narrow rail. The app is built for windows 1280px wide and wider; the page never scrolls
sideways, and each panel scrolls inside itself.

## Inspector

- **Pricing** holds the duration, **Calculate**, the total, Price Change, the out-of-date notice
  and the price list (see [pricing](pricing.md)). **Service** edits the selected service, adds a
  new SKU, or removes a service; with nothing selected it says "Select a service on the canvas".
- The top of each tab stays in view while the rest scrolls: duration, Calculate, total and Price
  Change in Pricing; the service heading and delete button in Service.
- **Merged** (the default): one tab at a time. Selecting a service, or choosing a SKU in the
  search, brings **Service** to the front; a finished calculation (including the automatic one
  when an architecture opens) brings **Pricing** to the front. Saving a service doesn't switch
  tabs.
- **Split**: drag either tab to the lower half to show both, one above the other, with a
  draggable divider. Drag the lower tab onto the upper tab bar to merge again, or the upper tab
  to the lower half to swap them. Each tab's menu offers the same actions from the keyboard.
- **Collapsed to its rail**: selecting a service expands it with Service in front. A finished
  calculation doesn't expand it; a marker on the rail shows there's a new result.

## Look

- Zinc greys with one blue accent, and a dark header. The app shows the light theme: dark-theme
  colours are defined and checked for contrast, but nothing switches them on yet. A theme toggle
  in the header is planned.
- Every control has visible hover, keyboard-focus and pressed states, and an accessible name.
  Text meets WCAG 2.1 AA contrast.
- Menus, tabs and panels animate in about 150–200ms, or not at all when the system asks for
  reduced motion.

## Settings saved to your account

These follow you to any browser or device, for guests and logged-in users alike:

- the sidebar and inspector widths, and whether each is collapsed;
- the inspector arrangement (merged or split, which tab is on top, the divider, the front tab);
- the last provider you used;
- the Trends selections (see [trends](trends.md)).

Settings saved by older versions in the browser are moved to the account once, on first load. A
setting that fails to save still applies for the session and is retried; it never blocks you.

These stay **in the browser**, per architecture, and don't follow you to another device or into
an export: box positions and sizes, icon arrangement inside boxes, connector bends and sides,
zoom, and the last calculation result.

## Specs

[007](../../specs/007-ui-overhaul-shadcn/spec.md),
[008](../../specs/008-ui-updates-corrections/spec.md),
[013](../../specs/013-column-resize-narrow-behavior/spec.md),
[019](../../specs/019-gcp-azure-providers-trends/spec.md) (US4),
[021](../../specs/021-workspace-layout-redesign/spec.md) (replaces the five-column layout of
007–013).
