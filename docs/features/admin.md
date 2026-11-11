# Admin

The **Admin** tab is shown only to the administrator, the built-in `Admin` account. It has two
sections: **User Management** and **System Information**.

## User Management

A table of every account, with its username, Active checkbox, password and Purge control.

- **Create a user** with just a username; it starts active, with no password. Duplicate
  usernames are refused. The user sets their own password at first login, or the Admin can set
  one.
- **Active**: unticking it stops the user logging in at their next check; their data is kept.
- **Password**: shows the last 4 characters of the stored hash with **Update**, or **Create**
  when there's no password. The password is entered in a dialog, stored only as a hash, and never
  shown back.
- **Purge** permanently removes a user and everything they own, after a confirmation.
- The `Admin` account can't be deactivated or purged.
- A restored database keeps every user's password; the owner password set in the cloud applies
  only to a fresh database (see [operations.md](../operations.md#cant-log-in-as-admin)).

### Import and export

Each user row has **Import Architectures from Disk** and **Export Architectures to Disk**. They're
separate from the Import in the architecture menu.

- **Export** downloads all of the user's architectures as one JSON file named
  `<username>_<timestamp>.json`, through the browser. It's disabled for a user with no
  architectures. The file holds everything needed to recreate them (collections, services,
  connectors, arrow styles), but no passwords, other users' IDs, prices, or per-browser layout.
- **Import** reads such a file from your computer into that user's account. A file that isn't
  valid JSON, isn't in the export format, or has a newer format version is rejected and nothing
  is imported. Otherwise each architecture is checked and imported on its own; one that fails
  (for example because the user already has one with that name) is skipped without leaving
  anything behind. A results table then shows each architecture's status. Imported architectures
  are private.

## System Information

Refreshes every minute while open, and has a **Check now** button that looks for new pricing
data straight away.

- **Deployment** and **Pricing data source**: where the app runs and where it reads prices from.
- **Providers**: for each provider, its status (see
  [provider status](providers-and-pricing-data.md#provider-status)), active snapshot, latest
  pipeline run and any failed regions, the last refused manifest and why, and when it was last
  checked.
- **Cache**: the local copy of an S3 snapshot.
- **Issues**: AWS services with no canvas icon, and regions the new active snapshot has no data
  for that the previous one had. Reporting GCP and Azure services with no icon is planned.

Not shown yet: each provider's Trends history status (weeks built, missing weeks, whether a
build is running or failed). The server already reports it; the page doesn't display it.

## Specs

[012](../../specs/012-user-accounts-sharing/spec.md) (US1),
[014](../../specs/014-architecture-templates-import-export/spec.md) (US2, US3),
[016](../../specs/016-canvas-icon-layout/spec.md) (US5),
[018](../../specs/018-app-cloud-deployment/spec.md),
[019](../../specs/019-gcp-azure-providers-trends/spec.md) (FR-009).
