# Changelog

Releases of the app, newest first. Each feature links to its specification folder, which has
the full design (spec, plan, tasks). Versions stay below 1.0.0 until a deliberate 1.0 release.

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
