# Contract: User menu and theme (UI)

## Trigger

The person icon at the left of the header. Accessible name: "User menu: Guest" or "User menu:
<username>". `aria-expanded` while open. Same `HeaderMenu` behaviour as the Cloud Pricing
chevron (research R1).

## Keyboard (both header menus)

| Key | On the trigger | In the menu |
|---|---|---|
| Enter, Space | open, focus the first item | activate the focused item |
| ArrowDown | open, focus the first item | next top-level item (wraps) |
| ArrowUp | — | previous top-level item (wraps) |
| Escape | — | close, focus returns to the trigger |
| Tab | — | close, focus moves on (Popover default) |

The Cloud Pricing menu keeps ArrowRight / ArrowLeft into and out of a provider's panel, and
Escape in a name field still clears the name first.

## Items, in order

1. A label: the username or **Guest** (not focusable).
2. **Log in** (guest) or **Log out** (logged-in user).
3. A **Settings** heading, then **Colour theme: Dark** in the light theme or **Colour theme:
   Light** in the dark theme.

No Change user.

## Actions

- **Log in**: closes the menu and opens today's `LoginDialog`; on success the identity's queries
  refetch and the app goes to `/` (today's behaviour), and the user's saved theme is applied.
- **Log out**: if `UnsavedWork.dirty`, shows `UnsavedWorkDialog` first (Cancel keeps the user
  logged in). Then: current identity ← guest ID; theme cache removed and `.dark` removed; query
  cache and preferences store cleared; navigate to `/`.
- **Colour theme**: toggles `.dark` on `<html>` at once and keeps the menu open on the item,
  which now offers the other theme. For a logged-in user, queues `appearance` for saving and
  writes the theme cache; for a guest, saves nothing.

## Reduced motion

Under `prefers-reduced-motion: reduce`, the menu opens with no animation and the theme switch
has no transition (existing global rule in `index.css`).
