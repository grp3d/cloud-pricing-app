# Feature Specification: On-Demand Cloud Deployment with Manifest-Driven Pricing Data

**Feature Branch**: `018-app-cloud-deployment`

**Created**: 2026-10-02

**Status**: Draft

**Input**: User description: "`../speckit-inputs/cloud-pricing-app-cloud-deployment.md`: bring up a complete, private instance of the app in the cloud with one action and destroy it with another, keeping user data across cycles, with pricing data read through the pipeline's manifests. In addition: the data-retrieval deployment feature is complete and its contracts (`latest.schema.json`, `manifest.schema.json`, `storage-layout.md`) are the source of truth; the web service must still run locally against local Parquet files, with a straightforward way to name the data source; and the deployment scripts and settings must apply the lessons from the data-retrieval repo's deployment review (last 4 commits on `003-pipeline-cloud-deployment`, last commit on `004-pipeline-cloud-deployment-fixes`, and `docs/backlog/003-pr-review-findings.md`)."

## Clarifications

### Session 2026-10-02

- Q: Which repository owns the deployment roles for the app? → A: This repository. A small one-time setup stack here creates the app's own roles, applied by the owner with administrator credentials. It refers to the account-wide items that already exist (the automation identity provider, the infrastructure state store, the budget) and does not create or change them. The data-retrieval repository is not changed.
- Q: Will more repositories deploy into this account later? → A: Possibly. The app's setup must refer to the account-wide items only by explicit inputs, so they could move to a shared account repository later without changing the app.
- Q: Is a domain name used in this release? → A: No. The app is reached by its public IP address. Domain names and automatic DNS updates are out of scope for this release.
- Q: How is the connection secured without a domain? → A: HTTPS with a self-signed certificate. The owner trusts it once on their devices. No public certificate authority is used.
- Q: Does the IP address stay the same across teardown and bring-up? → A: No. Each bring-up gets a new address, and "up" reports it. Nothing is paid for an address while the app is down.
- Q: Which version of the app does "up" deploy? → A: The newest tagged release (`v*`) by default, with an optional input naming a specific release. Merges to `main` are not deployed until they are tagged.
- Q: Should the app still read the old local layout (`snapshot_date=` folders with `_SUCCESS` markers)? → A: No. Only the pipeline's manifest layout is supported. The old data-directory setting (`AWS_PRICING_PARQUET_DIR`) is removed, and an old-layout directory is reported with instructions for producing a supported one.
- Q: How is the app reached from a phone on a mobile network, whose address changes often? → A: The allowlist holds fixed addresses only, changed with the one-action allowlist update. The phone normally uses home Wi-Fi or a VPN back home. A cellular address can be added by hand when needed and is removed by hand. Entries do not expire automatically.
- Q: If "up" cannot get a usable pricing snapshot, does it report failure or success? → A: Success with a warning. "Up" reports success but states that pricing is unavailable and why. The Admin tab shows the same, and the app starts pricing once a usable snapshot appears at a later check.
- Q: Should a forgotten instance only raise an alert, or also tear itself down after a longer limit? → A: Alert only, repeated at a configurable interval (default every 12 hours) while the instance stays up. There is no automatic teardown.

## Context

The app runs only on the owner's laptop today. It finds pricing data by scanning a local directory for `snapshot_date=` folders and `_SUCCESS` markers. The data pipeline (a separate repository) has since moved to a new storage layout, used identically for a local directory and for cloud storage, in which each snapshot is described by a **manifest** and a `latest` pointer names the newest good snapshot. The `_SUCCESS` markers are no longer produced.

This feature does two things:

1. **Pricing data from manifests.** The app reads snapshots through the pipeline's manifests, from either a local directory or cloud storage, chosen by one setting.
2. **On-demand cloud deployment.** The owner can create a complete private instance of the app in the cloud with one action and destroy it with another, paying almost nothing while it is down, and losing no user data.

The pipeline's published contracts are authoritative for the data format: `latest.schema.json`, `manifest.schema.json` and `storage-layout.md` (including its "Consumer rules") in `cloud-pricing-data-retrieval/specs/003-pipeline-cloud-deployment/contracts/`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The app reads pricing data through manifests, locally or from the cloud (Priority: P1)

A developer runs the app on their laptop, exactly as today, and points it at a pricing data location with a single setting. The location can be a local directory written by the pipeline or the pipeline's cloud storage. The app reads the `latest` pointer, loads the manifest it names, and uses only the data files that manifest lists. With a local directory, the app needs no cloud account, no credentials and no network.

**Why this priority**: Everything else depends on it. The cloud instance cannot get pricing data any other way, and the pipeline no longer writes the markers the app scans for today. It also delivers value on its own: local development keeps working against the pipeline's current output.

**Independent Test**: On a laptop with no cloud credentials, set the data source to a local directory in the pipeline's layout, start the backend and frontend with the existing start scripts, and price an architecture. Then change only the data-source setting to the cloud location (with read credentials) and see the same prices for the same snapshot.

**Acceptance Scenarios**:

1. **Given** the data source is a local directory in the pipeline's layout, **When** the app starts with no cloud credentials and no network, **Then** it serves prices from the snapshot the `latest` pointer names.
2. **Given** the data source is the pipeline's cloud storage, **When** the app starts, **Then** it copies the active snapshot's files to a local cache, verifies each file against the manifest's size and checksum, and only then serves prices from it.
3. **Given** a working local setup, **When** the developer changes only the data-source setting from a local directory to a cloud location or back, **Then** no other setting, code change or data conversion is needed for pricing to work.
4. **Given** a snapshot folder that holds files from more than one revision, **When** the app reads the snapshot, **Then** it uses only the files the manifest lists and counts no row twice.
5. **Given** a manifest with an unsupported major contract version or an unsupported table schema version, **When** the app reads it, **Then** it refuses that snapshot, keeps any snapshot already in use, and reports the reason in the Admin tab.
6. **Given** a manifest with status `partial`, `failed` or `purged`, **When** the app chooses a snapshot, **Then** it never makes that snapshot active.
7. **Given** a pinned snapshot date (`ACTIVE_SNAPSHOT_DATE`), **When** the app starts, **Then** it uses that date's manifest, fetching it if needed, and refuses to start if that snapshot is missing, purged or not `succeeded`.
8. **Given** the data-source setting is missing, malformed, or names a location that does not exist, **When** the app starts, **Then** it reports clearly which setting is wrong and what form is expected.

---

### User Story 2 - Bring the whole app up in the cloud with one action (Priority: P1)

The owner triggers "up", from a phone or a laptop. Without any further manual step, the infrastructure is created, the app starts, the database is restored from the latest backup, the current pricing snapshot is fetched and verified, and the action reports the address of the new instance. The owner opens that address over HTTPS, logs in and sees their saved architectures with current prices.

**Why this priority**: This is the feature's main purpose. Together with Story 1 it gives a usable cloud instance.

**Independent Test**: From a fully torn-down state with a backup present, trigger "up" once and do nothing else. Within the target time, open the reported address from an allowed network, log in and open a saved architecture.

**Acceptance Scenarios**:

1. **Given** the app is torn down and a backup exists, **When** the owner triggers "up", **Then** within 10 minutes the action reports the instance's address, and the app answers there over HTTPS with a certificate the owner's devices already trust, with the accounts and saved architectures from that backup.
2. **Given** a bring-up, **When** the database is restored, **Then** the restore is verified, pending schema changes are applied and standard seed data is applied without creating duplicates, all before the app is reported healthy.
3. **Given** a bring-up, **When** it finishes, **Then** the "up" action reports success, with the address, only after it has checked that the app is actually healthy there, and reports failure, with the failing step, otherwise.
4. **Given** no usable pricing snapshot can be obtained (source unreachable, nothing published yet, or verification failed), **When** "up" finishes, **Then** it reports success with a warning that pricing is unavailable and why. Login and saved architectures work, and pricing starts at a later check once a usable snapshot appears.
5. **Given** a bring-up that fails part-way, **When** the owner triggers "up" again or triggers "down", **Then** the action completes without manual clean-up.
6. **Given** the app is already up, **When** the owner triggers "up" again, **Then** nothing is duplicated and no data is lost.
7. **Given** either trigger (the hosted manual workflow or the local command), **When** it is used, **Then** the result is the same.
8. **Given** no release is named, **When** "up" runs, **Then** it deploys the newest tagged release and reports its version. **Given** an earlier release is named, **Then** that release is deployed instead.

---

### User Story 3 - Tear down safely, with no data loss (Priority: P1)

The owner triggers "down". The app takes a final database backup and verifies it. Only then is the instance destroyed. If the backup cannot be taken or verified, nothing is destroyed and the owner is told why. After teardown, the ongoing cost is close to zero.

**Why this priority**: Without a safe teardown the owner cannot stop paying for the instance without risking their data, which defeats the on-demand model.

**Independent Test**: With the app up, add a new saved architecture, trigger "down", then "up", and find the architecture present. Separately, make the backup location unwritable, trigger "down", and confirm the instance is still running.

**Acceptance Scenarios**:

1. **Given** the app is up, **When** the owner triggers "down", **Then** a final backup is taken and verified, and then every disposable resource is destroyed with no manual step.
2. **Given** the final backup fails or cannot be verified, **When** "down" runs, **Then** it stops before destroying anything and reports the reason.
3. **Given** a teardown has completed, **When** the owner reviews what remains, **Then** only the long-lived items remain (backups, the certificate root, release images, logs within their retention period, and the infrastructure state), and their monthly cost is within the "down" budget.
4. **Given** 10 consecutive down/up cycles with a change made in each, **When** the last cycle completes, **Then** every change is present.
5. **Given** the app is already down, **When** the owner triggers "down" again, **Then** it finishes successfully without error.
6. **Given** the app is up, **When** time passes, **Then** backups are also taken on a schedule, so a crash loses at most one backup interval of changes.

---

### User Story 4 - First-ever deployment into an empty environment (Priority: P2)

The owner deploys to an environment that has never held the app: no backup, no certificate root, no release image yet. After the documented one-time account setup, a single "up" produces a working app with a fresh database, standard seed data and an initial owner account whose credentials come from a secret.

**Why this priority**: It happens rarely, but it is where the pipeline's deployment went wrong (see "Lessons applied"). Every new environment (`qa`, `dev`) depends on it.

**Independent Test**: In an environment with nothing but the documented one-time setup, trigger "up" and log in with the initial owner credentials from the secret store.

**Acceptance Scenarios**:

1. **Given** an environment with no backup, **When** "up" runs, **Then** the database is created fresh, brought to the current schema and seeded, and an initial owner account is created from a secret.
2. **Given** an environment with no release image and no certificate root, **When** "up" runs, **Then** it creates or obtains what it needs in the right order and succeeds without a manual step.
3. **Given** the initial owner account already exists (restored from backup), **When** "up" runs, **Then** the account is neither duplicated nor has its password reset.
4. **Given** a new environment name (`qa` or `dev`), **When** the owner follows the one-time setup and triggers "up" for it, **Then** it comes up with its own data, backups, certificate root and address, with no code change, and without touching `prod`.

---

### User Story 5 - New pricing data is picked up while the app is running (Priority: P2)

While the app is up, the pipeline publishes a new snapshot, or a corrected revision of the current one. Within the check interval the app fetches and verifies the new data in the background, switches to it all at once, and removes local copies it no longer needs. The Admin tab shows what is active, what is cached, and the state of the latest pipeline run.

**Why this priority**: Prices stay current during long uptimes and the local disk does not fill. The app is still useful without it, because every bring-up already fetches the latest snapshot.

**Independent Test**: With the app running, publish a new `succeeded` snapshot to the data source. Within one check interval the Admin tab shows the new snapshot as active, requests made during the switch all succeed, and the previous snapshot's local copy is gone or within the configured keep count.

**Acceptance Scenarios**:

1. **Given** a newer `succeeded` snapshot is published, **When** the next check runs, **Then** the app fetches and verifies it in the background and then switches to it, and no request fails or sees mixed data during the switch.
2. **Given** a newer revision of the active snapshot date, **When** the next check runs, **Then** the app replaces its copy using the same fetch, verify, switch sequence.
3. **Given** the latest pipeline run is `partial` or `failed`, **When** the check runs, **Then** the app keeps the last `succeeded` snapshot, and the Admin tab shows the failed or partial run and its missing regions.
4. **Given** a snapshot already fetched and verified, **When** the app restarts or the check runs again, **Then** nothing is downloaded again.
5. **Given** a file fails its size or checksum check, **When** fetching, **Then** the snapshot is not activated, the current snapshot stays in use, the failure appears in the Admin tab, and the app tries again at the next check.
6. **Given** the data source cannot be reached, **When** the check runs, **Then** the app keeps serving the current snapshot and shows the error in the Admin tab.
7. **Given** the app starts with no usable snapshot, **When** pricing is requested, **Then** pricing requests return the existing "pricing data unavailable" error while login and saved architectures keep working.
8. **Given** cached snapshots beyond the keep count or the size limit, **When** clean-up runs, **Then** the excess is deleted, never including the active snapshot or one being read.

---

### User Story 6 - Private access only (Priority: P2)

The app is reachable only from the owner's allowed network addresses, only over HTTPS, at the instance's public IP address. There is no domain name in this release. The connection is secured with a self-signed certificate: the owner trusts the environment's certificate root once on each of their devices, and every later bring-up, at whatever new address, is trusted without a browser warning. When the owner's home address changes, they update the allowlist with one action. A phone normally reaches the app over home Wi-Fi or a VPN back home. On a mobile network, the owner adds the phone's current address by hand and removes it afterwards.

**Why this priority**: The app holds accounts and has only single-user hardening, so it must not be exposed. It ranks below Stories 2 and 3 only because they must exist before access can be restricted.

**Independent Test**: Trust the certificate root on a device once. From an allowed address, open the reported address and see a trusted HTTPS connection. From any other address, confirm the app cannot be reached at all. Tear down, bring up, and see the new address trusted without doing anything on the device. Change the allowlist and confirm the new address works without a teardown.

**Acceptance Scenarios**:

1. **Given** the app is up and the owner's device trusts the environment's certificate root, **When** the app is reached from an allowed address, **Then** it answers over HTTPS with no certificate warning, and the certificate names the instance's current address.
2. **Given** the app is up, **When** it is reached from any other address, on any port, **Then** the connection is refused or times out.
3. **Given** a request over plain HTTP, **When** it arrives from an allowed address, **Then** it is redirected to HTTPS or refused, and no login or session data is ever sent unencrypted.
4. **Given** a teardown and a new bring-up at a different address, **When** the owner opens the new address, **Then** the connection is trusted without any new step on their devices.
5. **Given** a first-ever deployment, **When** "up" finishes, **Then** the owner can obtain the certificate root to install, through an authenticated channel, and the runbook says how to trust it on a laptop and a phone.
6. **Given** the owner's address has changed, **When** they run the allowlist update, **Then** the new address can reach the app within 5 minutes, without a teardown and without data loss.
7. **Given** an address was added to the allowlist, **When** the app is torn down and brought up again, **Then** the address is still allowed until the owner removes it.
8. **Given** the owner needs a shell on the server, **When** they connect, **Then** they do so through an authenticated, keyless, audited channel, and no remote-login port is open to the internet.

---

### User Story 7 - Protection against a forgotten instance and cost overruns (Priority: P3)

The owner forgets to tear the app down. After a configurable time they receive an alert naming the environment and how long it has been up.

**Why this priority**: It protects the budget but does not affect whether the app works.

**Independent Test**: Set the threshold to a short time, bring the app up, wait, and receive the alert.

**Acceptance Scenarios**:

1. **Given** the app has been up longer than the configured threshold (default 12 hours), **When** the threshold passes, **Then** the owner receives an alert, and receives it again at a configurable interval (default every 12 hours) while the app stays up. The app is never torn down automatically.
2. **Given** the app is torn down, **When** time passes, **Then** no alert is sent.
3. **Given** the alert itself cannot be delivered or the check fails, **When** that happens, **Then** the failure is visible in the logs that survive teardown.

---

### User Story 8 - Run the production-like stack on a laptop (Priority: P3)

A developer runs the same packaged stack that the cloud runs, on a laptop, against a local data directory, to test backup and restore, database start-up and manifest sync before deploying. The existing non-packaged workflow (`bin/start_back.sh`, `bin/start_front.sh`) keeps working unchanged.

**Why this priority**: It shortens the feedback loop for deployment changes, but the cloud instance can ship without it.

**Independent Test**: On a laptop with no cloud credentials, start the packaged stack with its local settings, log in, price an architecture, take a backup, wipe the database, restart and find the data restored.

**Acceptance Scenarios**:

1. **Given** a laptop with no cloud credentials, **When** the packaged stack is started with local settings, **Then** the app works end to end against a local data directory and a local backup location.
2. **Given** the packaged stack on a laptop, **When** a backup is taken, the database is emptied and the stack is restarted, **Then** the data is restored and verified in the same way as in the cloud.
3. **Given** this feature is complete, **When** a developer uses the existing start scripts, **Then** they work as before, with only the data-source setting changed.

---

### Edge Cases

- The `latest` pointer does not exist yet (before the pipeline's first snapshot). The cloud storage reports a missing item as "access denied", so the app treats "access denied" on a missing item the same as "not found", and shows "no snapshot available" rather than a permissions error.
- The `latest` pointer names a manifest whose date differs, whose status is not `succeeded`, or whose revision is lower than the pointer's. The app rejects it and keeps the current snapshot.
- A manifest lists a file path that does not match the contract's layout, is absolute, contains `..`, or belongs to a different date. The app rejects the whole manifest before fetching anything, and never writes outside its cache.
- A fetch takes longer than the pipeline's grace period for superseded files, so a listed file has been deleted. The app re-reads the manifest and starts that fetch again.
- The snapshot is larger than the cache limit or the free disk space. The app does not activate it, keeps the current one, and reports the reason.
- The app restarts in the middle of a fetch. The partial copy is never used and is cleaned up.
- A local directory still in the old layout (`_SUCCESS` markers, no manifests) is configured. The app says the layout is unsupported and how to produce a supported one.
- The latest backup is corrupt or fails verification at bring-up. The app does not silently start with an empty database: bring-up fails and names the backup, and the owner can choose an earlier backup.
- The backup was taken by a newer version of the app than the one being deployed (a rollback). Bring-up fails with a clear message instead of running against a schema it does not know.
- "Down" is triggered while a scheduled backup or a snapshot fetch is running, or "up" and "down" are triggered at the same time. Only one of them proceeds, and the other waits or stops with a clear message.
- The owner's address changes while the app is up, and they are locked out. The allowlist update works from anywhere the owner can authenticate, not only from an allowed address.
- The certificate root is missing, unreadable or close to expiry at bring-up. A missing root on a first deployment is created. In any other case bring-up reports it clearly and says that devices will need to trust a new root. It never silently replaces a root the owner already trusts.
- The owner opens a bookmark to the previous bring-up's address. Nothing answers there. "Up" reports the current address, and the owner can ask for it again at any time.
- A deployment step reports success while the underlying action failed (for example, a start request accepted but nothing started). The action checks the actual outcome and fails.
- Teardown meets a resource that still holds content. Disposable resources are destroyed with their content, and long-lived resources are never part of teardown.
- The pinned snapshot date has been purged by the pipeline's retention. The app refuses to start, as today, and names the pin.

## Requirements *(mandatory)*

### Functional Requirements

#### Pricing data source

- **FR-001**: The app MUST take the location of pricing data from a single setting that accepts either a local directory or a cloud storage location. Changing between them MUST require changing only that setting (plus read credentials for a cloud location).
- **FR-002**: With a local directory as the source, the app MUST work with no cloud account, no credentials and no network access, and MUST read the files where they are without copying them.
- **FR-003**: Both kinds of source MUST use the pipeline's storage layout and be read through the same rules, so behavior does not differ by source apart from the local copy step (FR-009).
- **FR-004**: The app MUST find snapshots only through manifests: the `latest` pointer for the newest snapshot and the per-date manifest for a specific date. It MUST NOT scan data folders or look for `_SUCCESS` markers, and MUST use only the data files a manifest lists. The old layout is not supported: the old data-directory setting (`AWS_PRICING_PARQUET_DIR`) is removed, and a configured directory that has the old layout but no manifests MUST stop startup with a message saying how to produce a supported layout (run the pipeline locally, or convert old data with the pipeline's history-upload command). If the old setting is still set, startup MUST stop and name the setting that replaces it.
- **FR-005**: The active snapshot MUST be the one the `latest` pointer names, unless a date is pinned with the existing pin setting. A pinned snapshot that is missing, purged or not `succeeded` MUST stop startup with a clear message.
- **FR-006**: The app MUST accept only manifests whose status is `succeeded` and whose contract major version and table schema versions it supports. It MUST check that the manifest matches the pointer (same date, revision not lower).
- **FR-007**: The app MUST validate every file path in a manifest against the contract's layout, and that it belongs to the snapshot's date, before reading or fetching anything. A manifest with an invalid path MUST be rejected as a whole.
- **FR-008**: The app MUST treat "access denied" for a missing item the same as "not found".
- **FR-009**: With a cloud source, the app MUST copy the active snapshot's files to a local cache and verify each file's size and checksum against the manifest before use. The copy MUST go to a temporary place and replace the previous copy only when complete and verified, so that no reader ever sees a partial snapshot.
- **FR-010**: A snapshot revision that is already cached and verified MUST NOT be downloaded again, including after an app restart on the same host.
- **FR-011**: The cache MUST have a configurable size limit and keep the active snapshot plus a configurable number of others. A superseded snapshot within that number is kept. A snapshot that is purged, beyond that number, or over the size limit MUST be deleted at the next check after it becomes excess, so within one check interval. Clean-up MUST never delete a snapshot that is active or being read: a snapshot is never deleted by the same check that superseded it.
- **FR-012**: While running, the app MUST check for a newer snapshot or a newer revision of the active date at the existing configurable interval (default 5 minutes), and switch to it following FR-009. The owner MUST also be able to trigger a check from the Admin tab.
- **FR-013**: If the source cannot be reached or a new snapshot fails verification, the app MUST keep serving the current snapshot and report the problem. With no usable snapshot at startup, pricing requests MUST return the existing "pricing data unavailable" error while the rest of the app works.
- **FR-014**: The Admin tab MUST show: the active snapshot with its date, revision, regions and pipeline version; which source is configured; cache contents and size; the status of the latest pipeline run including failed regions; the last check time and any error; and the existing issues (missing icons, missing regions).
- **FR-015**: Snapshot reading and caching MUST be organized by provider, as the storage layout is, so another provider can be added later. Only AWS is implemented.
- **FR-016**: The design MUST NOT prevent a future feature from reading several historical snapshots at once (the price-trend tab). That feature is out of scope.
- **FR-017**: Missing prices keep today's behavior: a saved SKU with no price in the active snapshot shows the existing error.
- **FR-059**: Every response that returns prices or catalog rows MUST name the snapshot it came from by date **and revision**, so a price from a corrected revision is never shown under the same label as the price it replaced (constitution I).

#### Packaging and local running

- **FR-018**: The backend and frontend MUST be packaged as release images built automatically for each tagged release (`v*`), for the processor type of the chosen cloud server and for the developer's laptop. A release's images MUST NOT change once published, and building them MUST NOT depend on the instance being up.
- **FR-019**: One stack definition MUST run the whole app (web entry point with HTTPS, backend, database) on a single host, in the cloud and, with local settings, on a laptop (Story 8).
- **FR-020**: The existing non-packaged development workflow and the automated tests MUST keep working with no cloud access. The only required change for a developer is the data-source setting.

#### Database lifecycle

- **FR-021**: At startup in the cloud, the app MUST restore the database from the latest verified backup if one exists, or create it fresh if none exists. Then it MUST bring the schema up to date and apply seed data, both safe to repeat.
- **FR-022**: A restore MUST be verified before the app is reported healthy. A backup that exists but cannot be restored or verified MUST fail the bring-up. It MUST NOT lead to an empty database.
- **FR-023**: The owner MUST be able to bring up from a specific earlier backup.
- **FR-024**: On first deployment, an initial owner account MUST be created from a secret. No credential may appear in code, in images, or in logs. An existing account MUST NOT be overwritten.
- **FR-025**: Backups MUST be taken at teardown (FR-031) and on a configurable schedule while running (default every 6 hours), stored outside the instance, encrypted at rest, and not publicly readable.
- **FR-026**: The system MUST keep the most recent N backups (configurable, default 14) and delete older ones automatically. It MUST never delete the only verified backup.

#### Bring-up and teardown

- **FR-027**: One "up" action and one "down" action per environment MUST exist, each available both as a hosted manual trigger usable from a phone and as a local command, with the same result.
- **FR-057**: "Up" MUST deploy the newest tagged release by default, and MUST accept an optional input naming a specific release, which is how the owner rolls back. Untagged code from `main` is never deployed. "Up" MUST fail before creating anything if the named release, or any tagged release, has no published images, and MUST report which release it deployed. Running "up" with a different release on a running instance replaces the app version without data loss, following FR-021 and FR-022.
- **FR-028**: "Up" MUST create everything the instance needs, in an order that works from an empty environment, and MUST report success only after confirming the app is healthy at its address. "Healthy" means the app answers, the database is restored or initialized and verified, the owner account exists, and the login endpoint answers and rejects invalid credentials. The check MUST NOT depend on the owner's current password, which the owner may have changed in the app since first deployment (FR-024). A missing or unusable pricing snapshot does not make "up" fail: it reports success with a warning stating that pricing is unavailable and why (see FR-013).
- **FR-029**: "Up" and "down" MUST be safe to repeat and safe to run after a partial failure, with no manual clean-up. Any action that would replace a running instance, for whatever reason (a new release, a new server image, a different restore choice), MUST first take and verify a backup exactly as "down" does, and stop if that fails. The allowlist update MUST never replace the instance.
- **FR-030**: "Up" and "down" for the same environment MUST NOT run at the same time.
- **FR-031**: "Down" MUST take and verify a final backup before destroying anything, and MUST stop without destroying anything if that fails. A deliberate, explicitly named override MAY exist for an instance whose database is beyond recovery.
- **FR-032**: Nothing that holds app state may live on a resource that teardown destroys. Long-lived items (backups, the certificate root, release images, retained logs, infrastructure state) MUST be managed separately from the disposable instance, MUST survive teardown, and MUST never be removed by "down".
- **FR-033**: Teardown MUST destroy every disposable resource without manual steps, including resources that still hold content.
- **FR-034**: The infrastructure MUST take an environment name (`dev`, `qa`, `prod`). Only `prod` is deployed initially. Environments MUST NOT share data, backups, addresses or deployment permissions.

#### Access and networking

- **FR-035**: The app MUST be reachable at the instance's public IP address over HTTPS only, and only from a configurable list of allowed addresses. No other inbound access may exist. No domain name is used in this release.
- **FR-036**: The allowlist MUST be a list of fixed addresses, kept with the environment's settings. Adding or removing an address MUST take one action, from the hosted trigger and from the local command, without teardown, and the change MUST survive later down/up cycles. Entries do not expire automatically, and the action MUST show the full current list after each change so stale entries are visible.
- **FR-037**: HTTPS MUST use a self-signed certificate that does not depend on any public certificate authority. Each environment MUST have its own certificate root, created on first deployment and kept across rebuilds. Each bring-up MUST present a certificate, valid for the instance's current address, that devices trusting that root accept without a warning. The root's private key MUST be stored as a secret, and the owner MUST be able to obtain the public root to install on their devices.
- **FR-038**: Each bring-up gets a new public address. "Up" MUST report the address when it finishes, and the owner MUST be able to look up the current address of a running environment with one action, from the hosted trigger as well as the local command. Because the address is masked in automation logs (FR-050), both actions MUST also deliver it to the owner through the alert channel (FR-044). No address may be reserved, or paid for, while the environment is down.
- **FR-039**: Administrative shell access MUST use a keyless, authenticated, audited channel. No remote-login port may be open.
- **FR-040**: The layout MUST avoid always-on, fixed-cost network components unless their cost fits the budget and the need is recorded.

#### Secrets, permissions and logs

- **FR-041**: Secrets (database password, initial owner credentials, session secrets) MUST be held in a managed secret store and supplied at run time. They MUST NOT be in images, in the repository, or in logs.
- **FR-042**: The running app MUST have read-only access to pricing data (through the pipeline's published read permission), and read/write access only to its own backup location and its own certificate material.
- **FR-043**: Application logs MUST be kept somewhere that survives teardown, for a configurable short period (default 14 days).
- **FR-044**: An alert MUST be sent when an instance has been up longer than a configurable threshold (Story 7), and when a scheduled backup fails.

#### Deployment quality (lessons applied)

These requirements come from the review of the data pipeline's deployment work. See "Lessons applied" for the source of each.

- **FR-045**: Bring-up from an empty environment MUST be exercised end to end in a real account before the feature is accepted, and so MUST a full "down" followed by "up". A step that has only been planned or simulated does not count as verified.
- **FR-046**: Every one-time manual step (account setup, repository settings, trusting the certificate root on the owner's devices) MUST be listed in one runbook, in order, with a way to check that each was done. After that setup, no "up" or "down" may need a manual step.
- **FR-047**: Every deployment step MUST check the real outcome of what it started and fail loudly, naming the step. A request that is accepted but does nothing MUST count as a failure.
- **FR-048**: Deployment scripts MUST take their region, account and environment from explicit inputs. They MUST NOT depend on settings that happen to exist on the machine running them.
- **FR-056**: The deployment identities for this repository MUST be created by a one-time setup in this repository, run by the owner with administrator rights. That setup MUST refer to the account-wide items that already exist (the automation identity provider, the infrastructure state store, the budget) through explicit inputs, MUST NOT create, change or destroy them, and MUST NOT require any change to the data-retrieval repository. If an item it refers to does not exist, it MUST fail before creating anything, with a message that names the missing item. The runbook's check for that setup step (FR-046) MUST name the item as well.
- **FR-049**: The deployment identities for this repository MUST be separate for previewing changes, for publishing release images, and for making changes (bring-up, teardown, allowlist and other operations), limited to this repository and to named branches, tags or environments, and limited to the resources of their own environment. The full set of permissions each needs MUST be worked out and tested before first use, including cloud actions that cannot be limited to a named resource and account-wide prerequisites that the deployment identity is not allowed to create.
- **FR-050**: Because automation logs may be public, account identifiers and role identifiers MUST be masked in them, and stored as secrets rather than as plain settings.
- **FR-051**: A check MUST exist that shows which identity an automation run actually presents, so that trust rules can be verified against a real run before the first deployment.
- **FR-052**: Infrastructure definitions MUST have automated tests that run on every pull request with no cloud access, covering at least: what survives teardown, what is destroyed, the inbound access rules, and the permission boundaries. A preview of infrastructure changes MUST be shown on pull requests.
- **FR-053**: Tools, automation steps and downloaded binaries used for building and deploying MUST be pinned to exact versions, verified by checksum where they are downloaded, and locked for every platform they run on (hosted runners and the developer's laptop).
- **FR-054**: Documentation MUST describe the system as it is. First-time setup and routine operation MUST be separate sections, and docs MUST be updated in the same change as the behavior they describe.
- **FR-055**: Review findings that are investigated and found invalid MUST be recorded with their evidence, so they are not re-investigated.
- **FR-058**: Configuration complexity is a tradeoff to weigh in every design decision. The plan MUST list each setting, stored item, scheduled job, permission set and separately managed resource this feature adds, with the requirement that needs it. An option that adds any of these MUST say so when it is proposed, and the simpler option is preferred unless the benefit is stated.

### Key Entities

- **Pricing data source**: Where the app reads pricing data. Either a local directory or a cloud storage location, in the pipeline's layout. Chosen by one setting.
- **Latest pointer**: A small record per provider naming the newest `succeeded` snapshot: its date, revision and manifest location. Defined by `latest.schema.json`.
- **Snapshot manifest**: The authoritative description of one revision of one snapshot date: status, regions requested, succeeded and failed, pipeline run details, and for each table and region the list of data files with size, checksum and row count. Defined by `manifest.schema.json`.
- **Cached snapshot**: A verified local copy of one snapshot revision, identified by provider, date and revision. States: fetching, verified, active, superseded.
- **Database backup**: A point-in-time copy of user data (accounts, saved architectures) with the time taken, the app and schema version that produced it, and verification details.
- **Environment**: A named, isolated deployment (`dev`, `qa`, `prod`) with its own data, backups, address, allowlist and permissions.
- **Disposable instance**: Everything created by "up" and destroyed by "down". Holds no state that is not also in a backup.
- **Long-lived resources**: Items that survive teardown: backups, certificates, release images, retained logs, infrastructure state.
- **Access allowlist**: The network addresses allowed to reach an environment.
- **Certificate root**: An environment's own signing certificate and private key, created once and kept across rebuilds. The owner's devices trust its public part.
- **Instance certificate**: The HTTPS certificate presented by one bring-up, valid for that instance's address and accepted by devices that trust the certificate root.
- **Instance address**: The public IP address of a running instance. It changes on every bring-up.

## Lessons applied from the data pipeline's deployment review

Reviewed: commits `62c63ab`, `532abaa`, `d042ff8` and `493e896` on `003-pipeline-cloud-deployment`, commit `4dc4fed` on `004-pipeline-cloud-deployment-fixes`, and `docs/backlog/003-pr-review-findings.md`. No deployment standards exist yet, so the lessons are written here as requirements.

| What went wrong there | Lesson | Requirement |
|---|---|---|
| The image registry lived in the disposable stack. A fresh environment could not deploy itself (the image push ran before the registry existed), a one-off manual command was needed, and destroying the stack would either fail on a non-empty registry or delete the release images (finding R1, still open). | Separate long-lived resources from disposable ones. Order steps to work from zero. Teardown must cope with non-empty resources. | FR-028, FR-032, FR-033, FR-045 |
| The deployment role's permissions were completed only after the first real deploy failed several times: actions with no nameable resource, rules that need a tag at creation, an account-wide service role the deployment role may not create, and a missing read permission (`4dc4fed`). | Work out and test the full permission set, and identify account-wide prerequisites, before first use. Prove it with a real run. | FR-045, FR-049, FR-056 |
| A workflow printed a wrong link because it read the region from machine configuration that does not exist on hosted runners (`4dc4fed`). | Take region and environment from explicit inputs. | FR-048 |
| A start request returned success with a list of failures and no task, and the workflow carried on (`532abaa`). | Check real outcomes. | FR-047, FR-028 |
| Role and account identifiers were plain settings and appeared in public logs. Trust was by environment name only, then tightened to repository identity plus branch or tag (`62c63ab`). | Design trust narrowly and mask identifiers from the start. | FR-049, FR-050, FR-056 |
| The trust rules could only be confirmed by trying a deployment. A small "show my identity" workflow was added later (`62c63ab`), and two of the three roles were still unconfirmed at review time (R3). | Provide a way to verify identity before the first deploy. | FR-051 |
| The read permission allowed listing the whole bucket, then was narrowed, which changed "not found" into "access denied" for consumers (`532abaa`). | Grant least privilege from the start, and handle its side effects in the consumer. | FR-008, FR-042 |
| Manifest paths were followed without checking they stay inside the expected folder (R4, open). Snapshots with a non-`succeeded` status were accepted for upload (`493e896`, `d042ff8`). | Validate every path and status at the input boundary. | FR-006, FR-007 |
| The setup document described steps that no longer matched the real state, and mixed first-time setup with routine use (`532abaa`). | Keep docs true, and separate one-time from routine. | FR-046, FR-054 |
| Build actions were several major versions behind, and dependency lock files lacked checksums for some platforms (`62c63ab`, `4dc4fed`). A pinned helper binary's download location is known to change between versions (R2). | Pin and verify versions for every platform, and record how to upgrade. | FR-053 |
| Three review findings were invalid and took effort to disprove (R2, R3, R5). | Record disproved findings with evidence. | FR-055 |
| Infrastructure tests and pull-request previews were added part-way and caught trust-rule mistakes (`62c63ab`). | Have them from the start. | FR-052 |

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From a torn-down state, one "up" action gives a working app, with the owner logged in, their saved architectures present and current pricing (when a usable snapshot is published), in under 10 minutes and with no manual step.
- **SC-002**: 10 consecutive down/up cycles lose no user data, and after trusting the certificate root once the owner sees no certificate warning in any of them.
- **SC-003**: In an environment that has only had the documented one-time setup, the first "up" succeeds without any undocumented step, and a full "down" then "up" succeeds afterwards.
- **SC-004**: A developer with no cloud credentials can run the app locally against a local data directory by changing one setting, and the full automated test suite passes with no network access.
- **SC-005**: Each bring-up downloads the active snapshot at most once. Restarting the app with a warm cache downloads nothing.
- **SC-006**: The local cache never exceeds its configured limit, and snapshots beyond the keep count, or purged, are removed within one check interval of becoming excess.
- **SC-007**: A new `succeeded` snapshot becomes active within one check interval of being published, and no request fails during the switch.
- **SC-008**: 100% of attempts to reach the app from an address outside the allowlist fail, and from an allowed address the connection is encrypted and trusted by a device that has the certificate root.
- **SC-009**: The cost while down is $2 per month or less. Running 24 hours a day for a month keeps the whole project, including the pipeline, within its $20 to $30 monthly cap.
- **SC-010**: If the final backup fails, the instance is still running after "down" ends, in 100% of tests.
- **SC-011**: After an allowlist update, the new address can reach the app within 5 minutes.
- **SC-012**: An instance left up past the threshold produces an alert within 30 minutes of the threshold.
- **SC-013**: No account identifier, role identifier or secret appears in any automation log or in the repository.

## Assumptions

### Decisions already made (from the input)

- The cloud is AWS. Infrastructure is defined in OpenTofu, automation runs in GitHub Actions with short-lived federated credentials, and the app runs as Docker images under Docker Compose on a single server. Kubernetes is not used. These are fixed constraints for planning, not choices this spec leaves open.
- "Shutdown" means destroy and re-create. State lives in backups, not on a server or disk that survives.
- Single user for now. The existing accounts feature stays, with the allowlist and HTTPS on top.
- The two repositories stay separate. The only link to the pipeline is its stored data and manifests. There is no shared database.
- No expensive always-on network components (no NAT gateway, and no load balancer unless justified).

### Dependencies

- The data pipeline's cloud deployment is complete. Its bucket, manifests, `latest` pointer and read-only access policy exist, and its contracts are stable at major version 1.
- The account's one-time setup (remote infrastructure state, the automation identity provider, the account budget) exists, created by the data-retrieval repository. It grants deployment roles to that repository only, with permissions scoped to pipeline resources. This app creates its own deployment roles with a one-time setup in this repository (FR-056), and uses the existing account-wide items without changing them. More repositories may deploy to this account later, so the app refers to those items only through explicit inputs, and they can move to a shared account repository later without changing the app.
- The pipeline's finding R1 (where release images live) is still open there. This feature makes its own decision for the app's images (FR-032) and does not wait for it.

### Defaults chosen for the input's open questions

These are reasonable defaults. Each can be changed in `/speckit-clarify` without changing the shape of the spec.

- **Domain**: Resolved. No domain in this release (see Clarifications).
- **Server size**: The smallest size that prices one snapshot comfortably, confirmed by measurement during planning. The budget (SC-009) is the limit.
- **Release image storage**: Decided in planning. The requirements are only that images survive teardown and that the server can fetch them without long-lived credentials.
- **Snapshot checks**: Periodic while running (default 5 minutes), plus a manual check from the Admin tab (FR-012).
- **Forgotten instance**: Resolved. Alert only (see Clarifications).
- **Certificate root lifetime**: Long enough that routine use never needs devices to re-trust it (default 5 years). Replacing it is a deliberate, documented action.
- **Allowlist updates**: One action, from both the hosted trigger and the local command (FR-036).

### Other assumptions

- Developers' existing local data in the old layout must be converted or regenerated once before local development works again (FR-004).
- With a local directory, files are read in place and are not checksum-verified on every start. Verification applies to data copied from cloud storage.
- A developer may also point a laptop at the cloud data source, using the pipeline's existing off-cloud reader access. Setting up those credentials is the pipeline's documented process.
- Backup verification compares the restored data with details recorded at backup time (for example, per-table row counts). The exact method is a planning decision.
- A snapshot is about 145 MB. The default cache keeps the active snapshot plus one other.
- Losing up to one backup interval (default 6 hours) of changes after a crash is acceptable. A normal teardown loses nothing.
- Downtime while the app is torn down is expected and acceptable. High availability, autoscaling and multi-user hardening are out of scope.
- Domain names, DNS records and certificates from a public certificate authority are out of scope for this release. The design should not prevent adding a domain later.
- GCP and Azure data and tabs, the price-trend tab, and any change to the pipeline's code or data format are out of scope.
- The repository may be public, so automation logs are treated as public.
