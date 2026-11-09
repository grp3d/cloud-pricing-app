# Data Model: Workspace Layout Redesign (021)

No database tables change. The only stored data is the per-user preferences row from 019
(`user_preferences.data`, JSON validated by `Preferences` in `backend/src/models/schemas.py`),
which gains one optional field. The other "entities" here are UI state.

## 1. Inspector arrangement (stored: `workspace.inspector`)

| Field | Type | Values | Meaning |
|---|---|---|---|
| `mode` | enum | `merged`, `split` | One pane with two tabs, or two panes |
| `upper` | enum | `pricing`, `service` | Split: the tab in the upper pane. The other tab is in the lower pane. |
| `front` | enum | `pricing`, `service` | Merged: the visible tab |
| `split` | number | 0.2 to 0.8 | Split: the upper pane's share of the inspector's height |

**Validation (backend, `extra="forbid"`)**:
- All four fields are required when `inspector` is present.
- `split` is a float in [0.2, 0.8].
- Unknown keys or values return 422.
- `upper` and `front` are kept in both modes, so a split → merge → split round trip restores
  the previous split.

**Default (absent)**: `{ mode: "merged", upper: "pricing", front: "pricing", split: 0.5 }`
(spec Assumptions: starts merged, with Pricing in front).

**Display minimum**: when split, each pane renders at least its tab bar plus 120px of
content, whatever `split` says (FR-021). If the inspector is shorter than both minimums
together, it scrolls (spec Edge Cases).

### State transitions (`nextArrangement`, research R5)

| Action or event | When merged | When split |
|---|---|---|
| `select-tab(t)` (click or arrow key) | `front = t` | No change (both visible) |
| `drop-on-lower(t)` / menu "Move to lower half" on `t` | `mode = split`, `upper = other(t)` | If `t` is upper: swap (`upper = other(t)`). If `t` is already lower: no change. |
| `drop-on-upper-bar(t)` / menu "Merge" on `t` | No change | `mode = merged`, `front = t` |
| `swap` / menu "Swap" | No change | `upper = other(upper)` |
| `set-split(r)` (divider drag ends) | No change | `split = clamp(r, 0.2, 0.8)` |
| `service-selected` (canvas, Architecture Editor or catalogue SKU pick) | `front = service` | No change |
| `calculation-finished` (result or error, including the automatic one on open) | `front = pricing` | No change |
| Save of a service edit | No change | No change |
| Cancelled drag (Escape, or drop outside a zone) | No change | No change |

Only the listed events change the arrangement (FR-017). `other(pricing) = service` and the
reverse.

## 2. Workspace zone sizes (stored: `workspace.column_widths`, `workspace.collapsed`)

The existing keys are reused, so saved values carry over (FR-011).

| Zone | Width key | Default | Collapsed key | Notes |
|---|---|---|---|---|
| Left sidebar (Architecture Editor) | `col2` | 320px | `collapsed.col2` | Unchanged from today |
| Inspector | `col4` | 360px (was 288px for the Price Summary) | `collapsed.col4` (new use of an existing key) | The saved Price Summary width carries over |
| *Removed Column 1* | `col1` | — | `collapsed.col1` | No longer read; left stored |
| *Removed Column 3* | `col3` | — | `collapsed.col3` | No longer read; left stored |

**Validation**: unchanged. Widths must be positive integers. The drag minimum is 56px
(`MIN_WIDTH`, the rail).

**Rendered widths (`fitZones`, research R4)**:
- The canvas gets at least 400px.
- When the available width is too small, the sidebar shrinks first, then the inspector,
  each down to 56px.
- Fitting never changes the saved values.

## 3. Theme tokens (`frontend/src/index.css`)

The token names are unchanged; only the values change. Values are Tailwind v4's own OKLCH
palette.

| Token | Light | Dark |
|---|---|---|
| `--background` | zinc-50 `oklch(98.5% 0 0)` | zinc-950 `oklch(14.1% 0.005 285.823)` |
| `--foreground` | zinc-900 `oklch(21% 0.006 285.885)` | zinc-50 |
| `--card`, `--popover` | white `oklch(100% 0 0)` | zinc-900 |
| `--card-foreground`, `--popover-foreground` | zinc-900 | zinc-50 |
| `--muted`, `--secondary`, `--accent` | zinc-100 `oklch(96.7% 0.001 286.375)` | zinc-800 `oklch(27.4% 0.006 286.033)` |
| `--muted-foreground` | zinc-500 `oklch(55.2% 0.016 285.938)` | zinc-400 `oklch(70.5% 0.015 286.067)` |
| `--secondary-foreground`, `--accent-foreground` | zinc-900 | zinc-50 |
| `--border` (dividers, box outlines) | zinc-200 `oklch(92% 0.004 286.32)` | zinc-800 |
| `--input` (form control boundaries) | zinc-500 | zinc-500 |
| `--primary` | blue-600 `oklch(54.6% 0.245 262.881)` | blue-600 |
| `--primary-foreground` | white | white |
| `--ring` | blue-600 | blue-500 `oklch(62.3% 0.214 259.815)` |
| `--sidebar` | zinc-100 | zinc-900 `oklch(21% 0.006 285.885)` |
| `--sidebar-*` | Same mapping as the matching main tokens | Same mapping |
| `--destructive`, `--chart-*` | Unchanged | Unchanged |

**Contrast pairs asserted by the theme test (FR-031, research R8)**, in each theme:
- 4.5:1 or more:
  - `foreground` on `background`, `card` and `muted`;
  - `muted-foreground` on `background` and `card`;
  - `primary-foreground` on `primary`;
  - `sidebar-foreground` on `sidebar`.
- 3:1 or more: `ring` on `background` and `card`; `input` on `background` and `card`.
- `--border` is decorative (dividers and box outlines that are not a control's only
  boundary), so it is not held to 3:1.

## 4. Session-only UI state (not stored)

| State | Owner | Meaning |
|---|---|---|
| Architecture menu open | `ArchitectureMenu` | The Popover is open |
| Name being typed, per provider group | `ArchitectureMenu` | Text of an unconfirmed "New architecture…" |
| Drag in progress | `InspectorPanel` | The dragged tab and the hovered drop zone (none, upper bar or lower half) |
| New pricing result while collapsed | `WorkspacePage` | Shows the rail marker until the inspector is expanded (FR-018a) |
| Price per Sku word wrap | `PricingPanel` | Unchanged from today: off by default, for the session |
| Unsaved Service tab input | The Service tab (kept mounted) | Survives Pricing coming to the front (FR-017) |

The Service tab's content stays mounted while hidden, using Tabs' `forceMount` with
`hidden`, so unsaved input survives a tab switch.
