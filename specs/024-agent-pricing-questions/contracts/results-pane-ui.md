# Contract: Results Pane (Agent tab UI)

How the Agent tab looks and behaves with results (spec US6, FR-018–FR-020).

## Layout

```
┌ Agent tab body ──────────────────────────────────────────────────────────┐
│ Conversation (session header, messages, input) ┃ Results                 │
│                                                ┃ ◀ 2 of 2 ▶  [Download CSV] [×] │
│                                                ┃ title · basis lines      │
│                                                ┃ table (sticky header)    │
│                                                ┃ totals · not compared    │
└────────────────────────────────────────────────┸─────────────────────────┘
```

- **Divider**: `role="separator"`, `aria-orientation="vertical"`, `aria-valuenow` set to the
  conversation share in percent.
  - Dragging moves it; the arrow keys move it in 5% steps; Home and End go to the limits.
  - The range is 30–75%, default 45%.
  - It's saved to `workspace.agent_results.split` on release (debounced, like the other
    splits).
- **Narrow tab**: below 700 px of tab body width, Results stacks under the conversation, at
  full width and a minimum height of 240 px, with no divider. Going back above 700 px
  restores the side-by-side split.
- **Visibility**:
  - The pane is hidden while the session has no results.
  - A `result` event opens it and selects the new result.
  - × hides it.
  - Selecting a card, or a new result arriving, shows it again.
  - A new session clears everything.
  - Reopening a session that has results (for example after a reload) opens the pane on the
    latest result.

## Results pane content

- **Header**: ◀ ▶ step buttons (disabled at the ends) with the label "Result k of n", then
  "Download CSV", then "Close results" (×). Each button has an accessible name.
- **Title and basis**: the title; a line per provider (region, with "(guessed)" where it
  applies, the term and the snapshot date); duration; currency; and assumptions.
- **Table**: a `<table>` with a caption, a sticky header and right-aligned amounts.
  - Columns: service (and where, for architectures); then per side (a provider in a region),
    product and amount; and per target side, match quality, difference and %. A side's header
    shows the provider, and the region too when the same provider appears twice.
  - Differences show their sign. Increases and decreases aren't distinguished by colour alone
    (a sign and text).
  - A quality badge's tooltip lists the differences, and the agent's reason when it lowered
    the label.
  - Unavailable, unmatched and unconvertible cells show "Unavailable", "No equivalent" or
    "Can't convert usage", with the reason as a tooltip, and never a number.
- **Footer**: totals ("Total (partial)" where needed), and "Not compared:" followed by the
  unmatched and unpriceable services.
- **Formatting**: amounts use the app's USD formatter (2 decimal places); percentages use 1
  decimal place.

## Card in the conversation

- It sits under the agent message that produced the result: an icon, the title, and the
  summary line.
- It's a `button` labelled "Show result: <title>". Activating it opens the pane on that
  result.
- The card for the result currently shown is marked `aria-current="true"`.

## Download

- "Download CSV" fetches `GET /agent/session/results/{id}/csv` with the auth header, then
  saves the blob with the filename from `Content-Disposition`.
- On failure the button shows an inline error ("Couldn't download the result."). Nothing else
  changes.

## Agent off, guest, or no session

These cases are unchanged from 023: the Agent tab is inactive, so the pane never shows.
