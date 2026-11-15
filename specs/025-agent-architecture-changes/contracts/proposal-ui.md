# Contract: Proposal UI in 025

Builds on 024's Results pane (`contracts/results-pane-ui.md`). Text follows the rule that user
messages are brief and precise.

## Results pane: proposal view

Proposals and comparison results share the pane's ◀ ▶ sequence, in creation order.

- **Header**: the title, the architecture's name (or "New architecture" / "Import"), and a status
  badge: Pending, Stale, Accepted, Undone, Rejected, Superseded, Expired.
- **Changes**: three groups, Added, Changed and Removed, each item with its label and, for a
  change, before → after (quantity, term, size, name).
- **Cost**: before, after, difference and percentage for the total, then tables by service and by
  region. A create or import shows its cost only. "Total (partial)" when anything is unpriced,
  with the unpriced items listed under "Not priced". Contributions per group, in order, when the
  proposal has more than one group (US8). Figures are the engine's, rounded to the cent; the
  duration and snapshot are under the table.
- **Assumptions**: a list; guessed regions marked "(guess)".
- **Actions** (pending): **Accept** and **Reject**. Accept is disabled, with the reason, when the
  proposal's architecture isn't open ("Open Prod Web to accept this change.") or a message is
  being answered.
- **Stale**: the badge, and "Prod Web changed after this proposal was made." Accept re-checks
  first; the view then shows the new figures and **Accept updated proposal**.
- **Accepted**: **Undo**; after undo, **Redo**. When undo has ended, the buttons are gone and the
  reason is shown: "Your latest edit means the agent's previous change can no longer be undone."
  / "A later change replaced this one." / "The session has ended."

## Conversation: proposal card

Under the agent message: the title, the item count and the cost difference ("Prod Web · 6
changes · +$722.18 (+45.5%)", or the total for a new architecture). Selecting it shows the
proposal in the pane. Accepted cards carry the same **Undo** / **Redo** buttons and the same
end-of-undo text as the pane.

## Notice when undo ends

When a refetch shows that undo ended because of a manual edit, a toast appears once: "Your
latest edit means the agent's previous change can no longer be undone." (FR-006).

## Unsaved-work dialog (FR-017)

Shown when the agent opens another architecture while the open one has unsaved work:

- title: "Unsaved changes in '<name>'";
- text: "The agent is opening '<other name>'.";
- buttons: **Save and continue**, **Discard and continue**. There's no close button; Escape does
  nothing until one is chosen.
- If saving fails, the dialog shows the save error and stays, with both buttons.

## Accessibility

Buttons have text labels; status badges have text, not colour only; the dialog traps focus and
returns it to the conversation after closing.
