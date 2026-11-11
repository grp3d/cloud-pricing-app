# Operations

Bringing the app up and down, releases, backups, logs and troubleshooting. Every command takes
`--env <dev|qa|prod>` and needs `export AWS_REGION=us-east-1` and your AWS credentials. In
GitHub, use the **app** workflow with the matching `action`; it runs the same script with the
`deploy` role. The one-time setup is in [setup.md](setup.md).

- [Commands](#commands)
- [Up](#up) · [Down](#down) · [Status and the address](#status-and-the-address)
- [Releasing a new version](#releasing-a-new-version)
- [Backups and rollback](#backups-and-rollback)
- [Allowlist](#allowlist) · [The lock](#the-lock)
- [Logs and the shell](#logs-and-the-shell)
- [Forgotten instance](#forgotten-instance)
- [Updating the server image](#updating-the-server-image)
- [Pinned versions and upgrades](#pinned-versions-and-upgrades)
- [Exit codes and troubleshooting](#exit-codes-and-troubleshooting)

## Commands

| What | Laptop | GitHub **app** workflow |
|---|---|---|
| Bring it up | `deploy/app up --env prod` | `action=up` |
| Tear it down | `deploy/app down --env prod` | `action=down` |
| Where is it, is it up? | `deploy/app status --env prod` | `action=status` (the address is emailed) |
| Allow / remove an address | `deploy/app allow add 203.0.113.7 --env prod` / `allow remove …` | `action=allow-add` / `allow-remove` with `address` |
| List the allowlist | `deploy/app allow list --env prod` | `action=allow-list` |
| Back up now | `deploy/app backup-now --env prod` | `action=backup-now` |

## Up

`up` deploys the newest `v*` release present in both registries, unless you name one
(`--release v1.2.3`, which is also how you roll back). It:

1. checks the setup (AMI, owner password, allowlist, base stack, release images) and takes the
   operation lock;
2. makes sure the TLS root exists (it is created only on a first deploy);
3. plans the instance stack. **If the plan would replace a running instance** — a new release, a
   new AMI, or a different `--backup` — it first stops the app, takes a `redeploy` backup and
   requires it to be verified;
4. applies, waits for the SSM agent, then runs `ops health` on the instance;
5. reports the address (masked in GitHub) and emails it.

A missing pricing snapshot does not fail `up`: it succeeds with a warning, and pricing starts at
a later check once a snapshot is published.

To restore an older backup instead of the newest: `deploy/app up --env prod --backup <id>`
(ids come from `status` or the backup bucket). On a running instance this replaces it, after a
`redeploy` backup of the current state.

## Down

`down` stops the web and backend containers, takes a `teardown` backup, and destroys the
instance stack **only if the backup is verified**. Otherwise it stops with exit 4 and destroys
nothing. `--force-without-backup` (`force_without_backup` in GitHub) skips the backup; use it only
for a database that is beyond recovery, or after a failed bring-up that nobody used (see
[troubleshooting](#a-bring-up-fails-its-health-check)). Running `down` again when nothing is up
is fine.

## Status and the address

Each bring-up gets a new public IP; nothing is paid for an address while down. `status` prints
the instance, address, release, uptime, last backup and lock holder, and — because addresses are
masked in GitHub logs — also emails the address when the instance is running.

## Releasing a new version

Merges to `main` are not deployed; a release tag builds and publishes the images, and `up` runs
them. Versions stay below 1.0.0 until a deliberate 1.0 release.

1. **Merge to `main`** and wait for CI. A merge through a pull request also runs the instance
   plan preview, if it's turned on; a direct push by the repository admin skips it, which is fine
   because `up` plans the stack again.
2. **Note your rollback point**: `deploy/app status --env prod` prints the last backup. If prod
   is up, `deploy/app backup-now --env prod` takes a fresh one.
3. **New provider in this release?** Check its pricing data is published, for example
   `aws s3 ls s3://<data-bucket>/gcp/manifests/latest.json`. A provider without data is disabled
   with a warning; it doesn't fail the bring-up.
4. **Tag and push**: `git checkout main && git pull`, then
   `git tag -a vX.Y.Z -m "vX.Y.Z: …" && git push origin vX.Y.Z`. Wait for **Actions →
   release**: job **publish (prod)** green, with a `backend` and a `web` digest.
5. **Bring it up**: `deploy/app up --env prod` (or the **app** workflow). Every bring-up
   restores the newest verified backup, then runs the database migrations; there is no separate
   migration step. A running instance is replaced after a `redeploy` backup.
6. **Check**: the email says `release vX.Y.Z, database restored`; you can log in; the Admin tab
   shows each provider's snapshot. Add the release to [CHANGELOG.md](../CHANGELOG.md).

The registries keep the newest 5 releases, so a rollback can reach back 4 releases; an older one
must be re-published first (run **release** from that tag).

## Backups and rollback

- **When backups are taken**: every 6 hours while up, a `teardown` backup on `down`, a
  `redeploy` backup before an instance is replaced, and on `backup-now`. The newest 14 verified
  backups are kept, in `s3://<backup-bucket>/<env>/db/`.
- **Restore a chosen backup**: `deploy/app up --env prod --backup <id>`. Ids come from `status`
  or the bucket listing. On a running instance this replaces it, after a `redeploy` backup of the
  current state.
- **Roll back a release**: `deploy/app up --env prod --release vOLD`. If the newer release
  changed the database schema, its backups are refused by the older release ("from a newer
  release"), so also name the backup taken before the upgrade (step 2 above):
  `deploy/app up --env prod --release vOLD --backup <id>`. Anything entered after the upgrade is
  lost.
- **Seeding the cloud from local data**: with your AWS profile, run the local stack's backup
  ([development.md](development.md#the-production-stack-on-a-laptop)) with
  `BACKUP_URI=s3://<backup-bucket>/prod/db/` (and `AWS_PROFILE`, `AWS_REGION` passed into the
  `ops` container); the next cloud `up` from a fresh environment restores it.

## Allowlist

The allowlist is the SSM parameter `/cloud-pricing-app/<env>/allowlist`: single addresses only
(`/32` or `/128`), up to 50, kept across down/up cycles, with no expiry. A change applies to a
running instance within a minute or two, without a teardown. Entries never expire, so check the
printed list now and then and remove stale ones. On a mobile network, add the phone's current
address while you need it and remove it afterwards; normally use home Wi-Fi or a VPN back home.

## The lock

`up`, `down`, `allow add|remove` and `backup-now` take `locks/<env>.json` in the backup bucket
for their duration, and GitHub queues runs per environment. If a run died and left the lock, a
later run stops naming the holder; after 2 hours, `--break-lock` removes it.

## Logs and the shell

- Logs: CloudWatch Logs group `/cloud-pricing-app/<env>`, one stream per container, kept 14 days.
  The JSON records from the backend arrive as they are.
  Each stream is named after its container, `cloud-pricing-app-<service>-1` (`db-init`,
  `backend`, `web`, `db`):

  ```bash
  aws logs tail /cloud-pricing-app/prod --since 1h --follow
  aws logs tail /cloud-pricing-app/prod --since 1h --log-stream-name-prefix cloud-pricing-app-db-init
  ```
- Instance ID and address, without `deploy/app`:

  ```bash
  aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=cloud-pricing-app-prod" "Name=instance-state-name,Values=running" \
    --query 'Reservations[].Instances[].[InstanceId,PublicIpAddress]' --output text
  ```
- Shell: `aws ssm start-session --target <instance-id>` (needs the Session Manager plugin). No
  SSH port exists. On the instance: `cd /opt/app && sudo docker compose ps -a`,
  `sudo docker compose logs <service>`; the first-boot log is `/var/log/cloud-init-output.log`.

## Forgotten instance

After 12 hours up, an email says so, and again every 12 hours while it stays up. Nothing is torn
down automatically.

## Updating the server image

```bash
AWS_REGION=us-east-1 deploy/app ami-latest --env prod
```

Put the new ID in `infra/envs/prod.tfvars`, commit, and run `up`. Because the AMI changes, `up`
takes a `redeploy` backup and replaces the instance. From GitHub, the change must be on `main`
first. Run `allow` only after that `up`: it refuses to apply a plan that would replace the
instance.

---

## Pinned versions and upgrades

Everything that builds or deploys is pinned (FR-053). To upgrade one, change the pin, run the
checks, and merge.

| What | Where | How to upgrade |
|---|---|---|
| Base images (`python:3.12-slim-bookworm`, `node:20-bookworm-slim`, `caddy:2`, `postgres:18`, `ghcr.io/astral-sh/uv`) | `backend/Dockerfile`, `frontend/Dockerfile.web`, `compose.yaml` — `image:tag@sha256:…` | `docker buildx imagetools inspect <image:tag>` and copy the index digest |
| PostgreSQL apt signing key | `backend/Dockerfile` `PGDG_FINGERPRINT` (`B97B0AFC…ACCC4CF8`) | only if PGDG rotates its key; the build fails on a mismatch |
| GitHub Actions | `.github/workflows/*.yml`, `@<commit sha> # vX.Y.Z` | `git ls-remote --tags https://github.com/<owner>/<action> 'refs/tags/vX.*'` and pin the commit |
| OpenTofu | `app.yml`, `ci.yml` (`1.10.6`) | change both; `required_version` is `>= 1.10.0` |
| AWS provider | `infra/*/.terraform.lock.hcl` | `tofu providers lock -platform=linux_arm64 -platform=linux_amd64 -platform=darwin_arm64` in each stack |
| Server AMI | `infra/envs/<env>.tfvars` `ami_id` | `deploy/app ami-latest`, then `up` ([above](#updating-the-server-image)) |
| Host packages (`docker.io`, `docker-compose-v2`, `amazon-ecr-credential-helper`) | Ubuntu archive, apt-signed | follow the AMI |
| Python and npm dependencies | `backend/uv.lock`, `frontend/package-lock.json` | `uv lock`, `npm install` |

---

## Exit codes and troubleshooting

| Exit | Meaning | What to do |
|---|---|---|
| 0 | done (for `up`, possibly with a pricing warning) | — |
| 2 | bad usage or input (env, IP, release format) | fix the command; nothing changed |
| 3 | a precondition is missing: one-time setup step, release not in the registry, lock held, root missing with backups, `allow` would replace the instance | the message names it; nothing changed |
| 4 | a backup failed or wasn't verified | nothing was destroyed or replaced; check the backup bucket and the log group |
| 5 | the instance didn't become healthy | the stack is left for diagnosis; see [below](#a-bring-up-fails-its-health-check) before running `down` |

A failed `up` or `down` can always be re-run; neither needs manual clean-up.

### A bring-up fails its health check

`up` exits 5, the address doesn't answer, and the message names the reason, for example
`db-init has not finished` or `db-init failed: …`. The web server starts only after the backend,
and the backend only after `db-init` (restore and migrations) succeeds.

1. Read the `db-init` log (see [Logs and the shell](#logs-and-the-shell)). If there's no
   `db-init` stream at all, the containers never started: open a shell and check
   `/var/log/cloud-init-output.log` and `sudo docker compose ps -a`.
2. **Don't run a plain `down`.** It would back up the half-restored database, which then becomes
   the newest backup and is what the next `up` restores. If nobody used the instance, tear it
   down without a backup: `deploy/app down --env prod --force-without-backup`. The backup it
   restored from is untouched.
3. Fix the cause, release a new patch version, and `up` again. To run the old version meanwhile:
   `deploy/app up --env prod --release vOLD`.

### Can't log in as Admin

- The username is `Admin`, with a capital A: usernames are case-sensitive.
- A restored database keeps Admin's password from the backup. The owner password in SSM
  (`/cloud-pricing-app/<env>/owner-password`) applies only to a fresh database. Whether this
  bring-up restored or started fresh is in the `up` email (`database restored` or `fresh`) and
  the `db-init` log.

### Two "Address" emails

`up` sends one when it finishes, and `status` sends one each time it runs while the instance is
up. They name the same address unless an `up` replaced the instance in between.
