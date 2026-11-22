# Changelog

Releases of the app, newest first. Each feature links to its specification folder, which has
the full design (spec, plan, tasks). Versions stay below 1.0.0 until a deliberate 1.0 release.

## Unreleased

- 022 GCP and Azure standard architectures: the four standard designs on GCP and Azure, created once in every environment ([spec](specs/022-gcp-azure-standard-architectures/))
- 023 Agent foundation: an Agent tab beside the Canvas tab (they merge, split and swap like the inspector's tabs) that answers questions about the open architecture's contents and cost, and what can be imported, with figures from the pricing engine; sessions, an activity log, Admin agent settings, per-user preview and limits, and a global monthly cap; the agent is off by default. The Admin page now has three tabs: Agent Settings, User Management and System Information ([spec](specs/023-agent-foundation/))
- 024 Agent pricing questions: the agent compares prices across AWS, Azure and GCP for a kind of service, for the open architecture (or one category of it) against one or both other providers, and for a single product, stating the basis, region guesses and each match's quality (set by the app's rules), and never estimating a price it can't get. Comparisons appear as a table in a Results pane beside the conversation, with cards in the conversation, stepping between results and CSV download; long operations show progress and stop at the timeout setting ([spec](specs/024-agent-pricing-questions/))
- 025 Agent-built architectures: the agent proposes changes you review in the Results pane with the pricing engine's cost before and after: creating an architecture, adding, scaling, replicating to another region or removing components, and importing a public architecture as your own copy. Nothing is saved until you accept; Undo and Redo reverse or reapply everything one message changed, until you edit the architecture yourself. Opening a named architecture asks first about unsaved Service tab input ([spec](specs/025-agent-architecture-changes/))
- 026 Agent cross-cloud translation: the agent translates an AWS architecture to GCP or Azure as a new architecture you review in the Results pane: a mapping table with each match's quality and where it came from (the standard architectures' own matches, the app's automatic matches, or a partial match you chose), both totals and the difference on the matched services, with every caveat. Nothing is created until you accept; Undo and Redo work as for a new architecture ([spec](specs/026-agent-cross-cloud-translation/))
- 027 Deferred UI and Admin fixes: the person icon opens a user menu, like the Cloud Pricing menu, with Log in or Log out (back to the browser's guest) and a Colour theme setting (light or dark, saved for logged-in users); System Information shows only app-wide information at the top, then Providers and Issues tabs, with each provider's snapshot detail and Trends history status in its row, and lists GCP and Azure services with no canvas icon (first-party only, with a count of Marketplace ones); the GCP and Azure icon maps were regenerated on the current price lists (no icons changed) ([spec](specs/027-deferred-ui-admin-fixes/))
- The backend refuses to start against a database that isn't at the code's latest migration, and names the command to run
- Cloud Pricing reopens the last architecture you opened, instead of an empty workspace
- The canvas's zoom controls are in its top-left corner, so resizing the canvas no longer hides them
- Opening an architecture, or resizing the canvas, fits its diagram into the canvas, zooming out only

## v0.1.1 — 2026-11-10

- Fix: bringing the app up from a backup made by an older release failed. The restore check
  looked for tables that only the newer migrations create; it now checks the tables the backup
  has, and the migrations add the rest.
- Fix: when the database setup fails, the bring-up now stops at once with the real error,
  instead of waiting 10 minutes and reporting that setup "has not finished".

## v0.1.0 — 2026-11-10

- 019 GCP and Azure providers, Trends page, settings saved to the account, and diagram arrows ([spec](specs/019-gcp-azure-providers-trends/))
- 020 GCP and Azure service icons and Price Change fixes ([spec](specs/020-provider-icons-connector-fixes/))
- 021 Workspace redesign: header architecture menu, sidebar, canvas and Pricing/Service inspector, zinc and blue theme ([spec](specs/021-workspace-layout-redesign/))
- Deployment fixes found after v0.0.1 (the `deploy/app` command, CI roles and the runbook)

## v0.0.1 — 2026-10-06

The first release: everything built up to and including the cloud deployment.

- 001 Assemble an AWS architecture and price it ([spec](specs/001-assemble-price-aws-architecture/))
- 002 Nest application components inside VPCs ([spec](specs/002-vpc-component-nesting/))
- 003 Service selection improvements ([spec](specs/003-service-selection-improvements/))
- 004 Canvas and pricing improvements ([spec](specs/004-canvas-pricing-improvements/))
- 005 Resizable canvas and reliable box sizing ([spec](specs/005-resizable-canvas-boxes/))
- 006 Fix reserved-term pricing ([spec](specs/006-fix-reserved-pricing/))
- 007 Five-column workspace with shadcn/ui ([spec](specs/007-ui-overhaul-shadcn/))
- 008 UI updates and corrections ([spec](specs/008-ui-updates-corrections/))
- 009 UI fixes and enhancements ([spec](specs/009-ui-fixes-next-iteration/))
- 010 Regions on collections and pricing grouped by region ([spec](specs/010-multi-region-support/))
- 011 Canvas connectors and the pop-out canvas ([spec](specs/011-canvas-connector-popout/))
- 012 User accounts, administration and architecture sharing ([spec](specs/012-user-accounts-sharing/))
- 013 Architecture panel at narrow widths ([spec](specs/013-column-resize-narrow-behavior/))
- 014 Standard architectures and Admin import/export ([spec](specs/014-architecture-templates-import-export/))
- 015 AWS service icons on the canvas and pricing results kept per architecture ([spec](specs/015-canvas-service-icons/))
- 016 Draggable icon layout, active pricing snapshot and configurable settings ([spec](specs/016-canvas-icon-layout/))
- 017 Structured JSON logging ([spec](specs/017-structured-json-logging/))
- 018 On-demand AWS deployment with manifest-driven pricing data ([spec](specs/018-app-cloud-deployment/))
