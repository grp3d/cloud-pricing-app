# Quickstart and Validation: On-Demand Cloud Deployment

**Feature**: `018-app-cloud-deployment`

These scenarios prove the feature end to end. Commands and settings are defined in [contracts/](./contracts/). This file says what to run and what to expect. The full operator runbook is `docs/deployment.md`, written during implementation (FR-046, FR-054).

**Prerequisites**:

- **Laptop**: `uv`, Node 20, local Postgres. For part B: Docker Desktop or Colima. For parts C–I: AWS CLI v2, OpenTofu `1.10.6`, `openssl`, `jq`.
- **AWS account**: the account setup and the pipeline's data stack already exist (data-retrieval repo). At least one `succeeded` snapshot has been published to `cloud-pricing-data-prod-*`.

---

## A. Local development against a local data root (US1; SC-004)

1. Produce a new-layout local root from the legacy data, once, in the data-retrieval repo:

   ```bash
   PIPELINE_STORAGE_URI=file://$HOME/…/cloud-pricing/DATA/pipeline \
     <pipeline cli> upload-history --snapshot-date <D> --source $HOME/…/cloud-pricing/DATA
   ```

   **Expect** `DATA/pipeline/aws/manifests/latest.json` naming `<D>`.

2. In `backend/.env`, remove `AWS_PRICING_PARQUET_DIR` and set `PRICING_DATA_URI=file://$HOME/…/cloud-pricing/DATA/pipeline`.

3. Turn off Wi-Fi, run `bin/start_back.sh` and `bin/start_front.sh`, log in, and price a standard architecture.

   **Expect**: prices appear. The Admin tab shows source `local`, the active date and revision, and no cache section.

4. Put `AWS_PRICING_PARQUET_DIR` back into `.env` and restart.

   **Expect**: startup stops with the message naming `PRICING_DATA_URI`.

5. Point `PRICING_DATA_URI` at `…/DATA/pricing_aws/parquet` (the old layout).

   **Expect**: startup stops, saying the layout is unsupported and how to convert it.

6. Run `cd backend && uv run pytest`.

   **Expect**: all tests pass with no network access, including the manifest-selection cases (partial, failed, purged, bad path, unsupported version, revision lower than the pointer) and the cache-swap tests against a fake S3 store.

## B. Local packaged stack (US8)

1. Create the laptop TLS root with `deploy/app cert local --create`, and trust it in Keychain.

2. Start the stack:

   ```bash
   docker compose -f compose.yaml -f compose.local.yaml up --build
   ```

   It uses `PRICING_DATA_URI=file:///data` (bind mount of `DATA/pipeline`) and `BACKUP_URI=file:///backups`.

   **Expect**: `db-init` logs `"db": "fresh"`, and `https://localhost:8443` works with no warning. Log in as Admin with the password from `.env.local`.

3. Create an architecture, then run `docker compose run --rm ops backup --kind manual`.

   **Expect**: `verified: true`, and two files appear in `./.local-backups/`.

4. Run `docker compose down -v` (wiping the database volume), then `up` again.

   **Expect**: `db-init` logs `"db": "restored"`, and the architecture is there.

5. Optional: seed the cloud from local data. With `BACKUP_URI=s3://<backup-bucket>/prod/db/` and the owner's AWS profile, `docker compose run --rm ops backup --kind manual` uploads the laptop database, and the first cloud `up` restores it.

## C. One-time setup per environment (runbook outline; FR-046)

Each step has a check:

1. Set this repo's OIDC subject template to `["repo","context","ref"]`, as in the pipeline repo, using a temporary token.

   **Check**: the public API `…/actions/oidc/customization/sub` shows `use_default: false`.

2. Create the GitHub environment `prod` (deployment branch `main` only). Set the secrets `AWS_ROLE_PLAN_PROD`, `AWS_ROLE_DEPLOY_PROD` and `AWS_ROLE_RELEASE_PROD`, the variables `AWS_REGION` and `RELEASE_ENVIRONMENTS=["prod"]`, and later `AWS_PLAN_ENABLED`. Add a tag ruleset that limits creating, updating and deleting `v*` tags to yourself.

3. Put an `ami_id` from `deploy/app ami-latest --env prod` into `infra/envs/prod.tfvars`.

4. Apply the base stack from the laptop:

   ```bash
   cd infra/base
   tofu init -backend-config=../envs/prod.backend.hcl -backend-config="key=app/prod/base.tfstate"
   tofu apply -var-file=../envs/prod.tfvars
   ```

   with `TF_VAR_alert_email`.

   **Check**: `tofu plan` then shows "No changes". The outputs include the three role ARNs, the backup bucket and both ECR repositories.

5. Confirm the alert email subscription by clicking the link.

6. Create the owner password:

   ```bash
   aws ssm put-parameter --type SecureString --name /cloud-pricing-app/prod/owner-password …
   ```

7. Add your address with `deploy/app allow add <your-ip> --env prod`.

   **Expect** the list printed.

8. Run the `oidc-subject` workflow from `main`.

   **Check**: its `sub` equals the `deploy` entry in `tofu output gha_trust_subjects`.

9. Tag the first release: `git tag v1.0.0 && git push origin v1.0.0`.

   **Check**: `release.yml` succeeds, and `aws ecr describe-images --repository-name cloud-pricing-app-backend-prod` (and `-web-prod`) shows `v1.0.0`. Re-running the workflow for `v1.0.0` reports both images as already present and pushes nothing.

## D. First-ever bring-up (US4; SC-003)

1. Run the Actions workflow **app** with `action=up` and `environment=prod`, with no release named.

   **Expect** within 10 minutes:
   - it deploys `v1.0.0`
   - the log says a **new TLS root was created**
   - `db: fresh`
   - an email with `https://<ip>`

2. Install the root on your laptop and phone (`deploy/app cert --env prod --out prod-root.crt`, runbook steps). Open the address.

   **Expect**: no certificate warning. Log in as Admin with the SSM password. Standard architectures are present.

3. The Admin tab shows source `s3`, the active snapshot with its revision and regions, a cache with one entry, and the release `v1.0.0`.

## E. Down/up cycle with no data loss (US2, US3; SC-001, SC-002, SC-005)

1. Create an architecture, then run **app** `down`.

   **Expect**:
   - the backup `…-teardown-v1.0.0` is `verified: true`
   - the instance stack is destroyed
   - `deploy/app status` shows "down" and the backup
   - the base resources and the TLS root still exist

2. Run **app** `up`.

   **Expect** within 10 minutes: `db: restored`, the architecture is present, a different IP is in the email, no certificate warning, and the cache downloaded the snapshot once.

3. Run `up` again while it's up, with the same release.

   **Expect**: OpenTofu reports no changes, the health check passes, nothing is duplicated, and the cache downloads nothing.

4. Tag `v1.0.1` and run `up` while it's up.

   **Expect**: a `redeploy` backup is taken and verified first, then the instance is replaced and restored from that backup on `v1.0.1`. No data is lost.

5. Update `ami_id` in `infra/envs/prod.tfvars` (from `deploy/app ami-latest`, or any other valid Ubuntu 24.04 arm64 AMI if it hasn't changed), make a change in the app, then run `deploy/app up` from the laptop with the same release. The workflow would only see a committed `tfvars` change.

   **Expect**: a `redeploy` backup is taken and verified **before** the instance is replaced, and the change is present afterwards (FR-029).

6. In the Admin tab, change the Admin password, then run `up` again.

   **Expect**: `up` reports healthy. The health check doesn't use the owner password from SSM (FR-028), and the new password still works.

7. Run **app** `status` from the GitHub workflow (from the phone).

   **Expect**: the address is masked in the job log, and an email with the current address arrives (FR-038).

8. Price a saved architecture.

   **Expect**: the pricing panel shows the snapshot date with its revision, for example `2026-10-05 r1`, matching the Admin tab (FR-059).

9. Repeat steps 1–2 ten times, which can be scripted from the laptop.

   **Expect**: all data is present, and there is no certificate step on any device.

## F. Backup failure blocks teardown (SC-010)

1. Temporarily deny `s3:PutObject` on `<env>/db/*` with a bucket policy statement (runbook test step), then run `down`.

   **Expect**: exit `4`, "nothing destroyed", and the instance still answers.

2. Remove the statement and run `down`.

   **Expect**: it succeeds.

## G. Access restrictions (US6; SC-008, SC-011)

1. From a non-allowlisted network (for example a phone on cellular), open the address.

   **Expect**: a timeout.

2. Run `curl -v http://<ip>` and `nc -vz <ip> 22` from an allowed address.

   **Expect**: both refused or timing out.

3. Run `deploy/app allow add <phone-ip>`.

   **Expect** within 5 minutes: the phone loads the app. Run `allow remove`, and it stops. `deploy/app status` shows the same instance ID and uptime as before: the allowlist change did not replace the instance (FR-029).

4. Run `down`, then `up`.

   **Expect**: the allowlist is unchanged.

5. Run `aws ssm start-session --target <instance-id>`.

   **Expect**: a shell with no SSH key.

## H. New pricing data while running (US5; SC-006, SC-007)

1. Publish a new succeeded snapshot, or a new revision of the active date, with the pipeline.

   **Expect** within 5 minutes (one check interval):
   - the Admin tab shows the new date and revision
   - a request loop running throughout has no failed requests
   - the previous cache entry is still there (it is within `PRICING_CACHE_KEEP=1`), and the cache stays under its limit
   - publish one more snapshot: once it is active, the oldest entry (now beyond the keep count) is gone by the next check, about 5 minutes later (FR-011, SC-006)

2. Publish a `partial` run.

   **Expect**: the active snapshot is unchanged, and "Latest pipeline run: partial" is shown with its failed regions.

3. Use the Admin tab's **Check now** button.

   **Expect**: the check runs immediately.

## I. Release selection, pricing unavailable, forgotten instance (FR-057; Story 2 AS4; Story 7)

1. Run `up` with `release=v0.9.9`, which doesn't exist.

   **Expect**: exit `3` before anything is created, with "release v0.9.9 is not in this environment's registry".

2. In a test environment such as `dev`, use a data source with no snapshot.

   **Expect**: `up` succeeds with the warning "pricing unavailable: no snapshot published", and login works.

3. With `UPTIME_ALERT_HOURS=1` set for a test, leave the app up.

   **Expect**: an alert email within 90 minutes, repeated at the repeat interval. It is never torn down automatically.

## Measurements to record before acceptance

- Peak memory on `t4g.small` during the standard-architecture pricing tests (research R3).
- Bring-up time for a fresh deploy and a restore (SC-001).
- The first real CI `up` and `down`, with no permission errors (FR-045). Any permission added afterwards goes into `infra/base` together with a test.
