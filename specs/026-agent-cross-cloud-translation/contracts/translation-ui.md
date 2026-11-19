# Contract: Translation in the Results Pane and Conversation

**Feature**: 026 | Extends 025's proposal view and card; no new pages and no Admin UI.

## Proposal view (`AgentProposalView`, kind `translate`)

Top to bottom:

1. **Heading**: "<source name> (AWS) → <target provider>" and the status, as 025.
2. **Regions and term**: "us-east-1 → eastus (a guess)", "Pricing: on demand — the original uses
   reserved 1-year; terms don't carry over".
3. **Mapping table**, one row per source service, in canvas order, grouped by collection:

   | Column | Content |
   |---|---|
   | Original | label, region, usage |
   | Match | label, size, usage — or the reason there is none, in muted text |
   | Quality | Exact / Close / Partial badge |
   | From | Seeded / Automatic / Chosen by you |
   | Differences | the app's facts, then assumptions |
   | Original cost, Match cost | engine amounts, 2 decimals; "—" when left out or unpriceable |

   Rows left out are shown with their reason ("No equivalent", "Not sold in eastus", "Only a
   partial match: ask the agent to use it"). "Chosen by you" rows have a note: "Partial match you
   chose; not checked as equivalent."
4. **Cost difference**: both totals ("partial" when anything is missing), the difference on
   matched services with its percentage ("On the 14 matched services: −$412.10, −18.2%"), the
   left-out list, up to three drivers, and both snapshot dates.
5. **Actions**: Accept and Reject, as 025. A stale translation shows "The original or the
   pricing data changed. Ask the agent to translate it again." and no Accept.

## Card (`AgentProposalCard`)

"Translation of Prod Web to Azure — on matched services −$412.10 (−18.2%), 2 left out", with
025's status, Undo and Redo. Accepting opens the new architecture, as 025's create does.

## Accessibility and layout

The table scrolls horizontally inside the pane at narrow widths; badges have text, not only
colour; the "From" column is plain text.
