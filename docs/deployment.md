# Deployment runbook

How to run the app in AWS on demand: bring it up with one action, tear it down with another, and
keep every user's data across cycles (feature `018-app-cloud-deployment`). The same commands work
from a laptop (`deploy/app`) and from GitHub (the **app** workflow, usable from a phone).

- [What runs where](#what-runs-where)
- [One-time setup](#one-time-setup) — once per AWS account and environment
- [Routine operation](#routine-operation) — up, down, status, allowlist, backups, releases
- [Certificates and devices](#certificates-and-devices)
- [The production stack on a laptop](#the-production-stack-on-a-laptop)
- [Pinned versions and upgrades](#pinned-versions-and-upgrades)
- [Exit codes and troubleshooting](#exit-codes-and-troubleshooting)
- [Answered questions](#answered-questions)

## What runs where

| Piece | Where | Survives `down` |
|---|---|---|
| The app: Caddy (HTTPS) + backend + Postgres, under Docker Compose | one `t4g.small` Ubuntu 24.04 instance (`infra/instance`) | **no** — destroyed |
| Database backups and the operation lock | S3 `cloud-pricing-app-backups-<env>-<suffix>` (`infra/base`) | yes |
| Release images | ECR `cloud-pricing-app-{backend,web}-<env>` (`infra/base`) | yes |
| TLS root, owner password, allowlist | SSM Parameter Store `/cloud-pricing-app/<env>/…` | yes |
| Logs (14 days) and alert email topic | CloudWatch `/cloud-pricing-app/<env>`, SNS `cloud-pricing-app-alerts-<env>` | yes |
| CI roles `plan`, `release`, `deploy` and the instance role | IAM (`infra/base`) | yes |
| Pricing data | the pipeline's bucket, read-only | (not ours) |

Nothing that holds state lives on the instance: every bring-up restores the newest verified
backup, and every teardown takes and verifies a final one first. While down, the cost is
storage only (about $0.30 a month).

The app is reached at the instance's public IP over HTTPS only, from allowlisted addresses only.
There is no domain name. HTTPS uses the environment's own certificate root, which you trust once
on each device. There is no SSH: the shell is Session Manager.

### Laptop tools

`deploy/app` needs **AWS CLI v2**, **OpenTofu ≥ 1.10** (CI uses 1.10.6), **jq** and **openssl**,
plus AWS credentials (your profile; `AWS_PROFILE` works). It never reads the region from AWS
config files: always set `AWS_REGION` (here `us-east-1`). The local packaged stack also needs
Docker.

---

## One-time setup

Once per environment (`prod` first), in order. Each step: **where**, **do**, **expect**. After
this, no `up` or `down` needs a manual step.

**Laptop prerequisites** for every laptop step: terminal at the repo root, your AWS administrator
profile active (`export AWS_PROFILE=…` if it isn't the default), and `export AWS_REGION=us-east-1`.

### 1. Check the account-wide items exist

**Where**: laptop, repo root.
**Do**: paste:

```bash
aws iam list-open-id-connect-providers --output text | grep -q token.actions.githubusercontent.com \
  && echo "ok   GitHub OIDC provider" || echo "MISSING: GitHub OIDC provider (cloud-pricing-data-retrieval bootstrap)"
for b in cloud-pricing-shared-tfstate-g08a9i cloud-pricing-data-prod-g08a9i; do
  aws s3api head-bucket --bucket "$b" 2>/dev/null && echo "ok   bucket $b" || echo "MISSING: bucket $b (cloud-pricing-data-retrieval)"
done
aws iam list-policies --scope Local --query "Policies[?PolicyName=='cloud-pricing-data-read-prod'].Arn" --output text | grep -q arn \
  && echo "ok   policy cloud-pricing-data-read-prod" || echo "MISSING: policy cloud-pricing-data-read-prod (pipeline data stack)"
```

**Expect**: four lines starting `ok`. A `MISSING:` line names what the pipeline repo must create first.

### 2. Set the repository's OIDC subject template

**Where**: GitHub (token), then laptop.
**Do**:

1. GitHub → your avatar → **Settings** → **Developer settings** → **Personal access tokens** →
   **Fine-grained tokens** → **Generate new token**: expiration 1 day; **Repository access** →
   *Only select repositories* → `cloud-pricing-app`; **Permissions** → **+ Add permissions** →
   **Actions** → set to **Read and write**. Generate and copy it (`github_pat_…`).
2. Laptop:

   ```bash
   read -rs GH_TOKEN   # paste the token, Enter
   curl -L -X PUT -H "Accept: application/vnd.github+json" -H "Authorization: Bearer $GH_TOKEN" \
     https://api.github.com/repos/grp3d/cloud-pricing-app/actions/oidc/customization/sub \
     -d '{"use_default": false, "use_immutable_subject": true, "include_claim_keys": ["repo", "context", "ref"]}'
   unset GH_TOKEN
   curl -s https://api.github.com/repos/grp3d/cloud-pricing-app/actions/oidc/customization/sub
   ```

3. GitHub → same token page → the token → **Delete**.

**Expect**: the last `curl` shows `"use_default": false`, the keys `repo`, `context`, `ref`, and
`"sub_claim_prefix": "repo:grp3d@5554338/cloud-pricing-app@1378579975"`.

### 3. Pick the server image

**Where**: laptop, repo root.
**Do**:

```bash
deploy/app ami-latest --env prod
```

Replace `REPLACE-ME` in `infra/envs/prod.tfvars` (`ami_id = "…"`) with the printed `ami-…`, then
commit and push it on your working branch.

**Expect**: an ID like `ami-0bec8cef5313300ad`.

### 4. Apply the base stack

**Where**: laptop, `infra/base` (administrator credentials).
**Do**:

```bash
cd infra/base
tofu init -backend-config=../envs/prod.backend.hcl -backend-config="key=app/prod/base.tfstate"
export TF_VAR_alert_email=you@example.com
tofu apply -var-file=../envs/prod.tfvars     # review, type yes
tofu plan -var-file=../envs/prod.tfvars
tofu output
```

**Expect**: `apply` completes; `plan` says **No changes**; `output` lists `role_arns` (`deploy`,
`plan`, `release`), `backup_bucket`, `repository_urls`, `gha_trust_subjects`.
If a command was interrupted and the next one reports *Error acquiring the state lock*, and no
other `tofu` is running: `tofu force-unlock <ID from the message>`.

### 5. Confirm the alert email

**Where**: your inbox (the `alert_email` address), then laptop.
**Do**: open "AWS Notification - Subscription Confirmation" → **Confirm subscription**. Then:

```bash
aws sns list-subscriptions-by-topic --topic-arn "$(cd infra/base && tofu output -raw alert_topic_arn)" \
  --query 'Subscriptions[].SubscriptionArn' --output text
```

**Expect**: an ARN ending in a UUID, not `PendingConfirmation`. The link expires after 3 days.

### 6. Store the owner password

**Where**: laptop.
**Do** (typed without echo, so it isn't in shell history):

```bash
read -rs PW && aws ssm put-parameter --type SecureString \
  --name /cloud-pricing-app/prod/owner-password --value "$PW" && unset PW
aws ssm get-parameter --name /cloud-pricing-app/prod/owner-password --query Parameter.Type
```

**Expect**: `"SecureString"`. It's the `Admin` password for a **fresh** database only; a restored
database keeps its own, so changing it in the app later is fine.

### 7. Allow your address

**Where**: laptop, repo root.
**Do**:

```bash
deploy/app allow add "$(curl -s https://checkip.amazonaws.com)" --env prod
```

**Expect**: the printed list shows your address as `…/32`. (Remove one later with
`deploy/app allow remove <ip> --env prod`.)

### 8. Merge, then configure GitHub

**Where**: GitHub. **Do**, in order:

1. **Merge** the feature PR into `main` (it carries the workflows and the `ami_id`).
2. **Environment** — repo → **Settings** → **Environments** → **New environment** → `prod` →
   **Configure environment** → **Deployment branches and tags** → *Selected branches and tags* →
   **Add deployment branch or tag rule** → `main` → **Add rule**.
3. **Secrets** — values from laptop, `infra/base`: `tofu output -json role_arns | jq -r .deploy`
   (and `.release`, `.plan`). Paste them only into these fields:

   | Secret | Where to add it | Why there |
   |---|---|---|
   | `AWS_ROLE_DEPLOY_PROD` = `.deploy` | Settings → Environments → `prod` → **Environment secrets** → **Add environment secret** | the **app** workflow runs in `prod`, which also limits it to `main` |
   | `AWS_ROLE_RELEASE_PROD` = `.release` | Settings → **Secrets and variables** → **Actions** → **Secrets** → **New repository secret** | the **release** job has no environment |
   | `AWS_ROLE_PLAN_PROD` = `.plan` | same as above | the CI `plan` job has no environment |

4. **Variables** — Settings → **Secrets and variables** → **Actions** → **Variables** →
   **New repository variable**: `AWS_REGION` = `us-east-1`; `RELEASE_ENVIRONMENTS` = `["prod"]`.
   Don't add `AWS_PLAN_ENABLED` yet (step 11).
5. **Tag ruleset** — Settings → **Rules** → **Rulesets** → **New ruleset** → **New tag ruleset**:
   name `release-tags`; Enforcement **Active**; **Bypass list** → add **Repository admin**;
   **Target tags** → **Add target** → *Include by pattern* `v*`; rules **Restrict creations**,
   **Restrict updates**, **Restrict deletions** → **Create**. (A tag push publishes images, so
   only you may create `v*` tags.)
6. **Branch ruleset** — same page → **New branch ruleset**: name `main`; Enforcement **Active**;
   Bypass list **Repository admin**; target **Include default branch**; rules **Restrict
   deletions**, **Block force pushes**, **Require a pull request before merging** → **Create**.
7. **Check** — **Actions** → **oidc-subject** → **Run workflow** → branch `main` → **Run workflow**;
   open the run → job **show** → step **Run actions/github-script**.

**Expect** (item 7): `sub:` starts with `repo:grp3d@5554338/cloud-pricing-app@1378579975:` and names
`refs/heads/main` (e.g. `…:ref:refs/heads/main:ref:refs/heads/main`); `ref: refs/heads/main`. Any
other prefix: step 2 didn't apply — fix it before step 9. Each role is then confirmed by its first
real use: release (step 9), deploy (step 10), plan (step 11).

### 9. Publish the first release

**Where**: laptop, then GitHub.
**Do**:

```bash
git checkout main && git pull
git tag -a v1.0.0 -m "v1.0.0: first cloud release"   # annotated: records who, when, why
git push origin v1.0.0
```

Then GitHub → **Actions** → **release** → the `v1.0.0` run.

**Expect**: job **publish (prod)** green; its **Summary** lists a `backend` and a `web` digest.
Laptop cross-check:
`aws ecr describe-images --repository-name cloud-pricing-app-backend-prod --query 'imageDetails[].imageTags'`
→ `v1.0.0` (same for `cloud-pricing-app-web-prod`).

### 10. First bring-up

**Where**: GitHub, then laptop and your devices.
**Do**:

1. GitHub → **Actions** → **app** → **Run workflow** → branch `main`, action `up`, environment
   `prod` (leave the rest empty) → **Run workflow**.
2. Laptop: `deploy/app cert --env prod --out prod-root.crt`; trust it on each device
   ([Certificates and devices](#certificates-and-devices)).
3. Browser: open the `https://<ip>` from the email; log in as `Admin` with the step 6 password.

**Expect**: within 10 minutes the run's **deploy/app** step shows `NEW ROOT CREATED` and
`prod is up at https://*** (release v1.0.0, database fresh).`; an email with the address arrives; the page opens with no
certificate warning and shows the standard architectures.

### 11. Optional: turn on PR previews

**Where**: GitHub.
**Do**:

1. Settings → **Secrets and variables** → **Actions** → **Variables** → **New repository variable**:
   `AWS_PLAN_ENABLED` = `true` (exactly).
2. Open a small pull request (or push to an open one).

**Expect**: the PR's **CI / plan** check green, and a PR comment `infra/instance plan (prod, vX.Y.Z)`
with `- no changes`. On failure: *Not authorized to perform sts:AssumeRoleWithWebIdentity* = trust
mismatch; *AccessDenied* during `tofu plan` = missing read permission (fix in `infra/base` with a
test assertion, never in the console). Set the variable to `false` to skip the job meanwhile.

---

## Routine operation

Every command takes `--env <dev|qa|prod>` and needs `AWS_REGION`. In GitHub, use the **app**
workflow with the matching `action`; it runs the same script with the `deploy` role.

| What | Laptop | GitHub **app** workflow |
|---|---|---|
| Bring it up | `deploy/app up --env prod` | `action=up` |
| Tear it down | `deploy/app down --env prod` | `action=down` |
| Where is it, is it up? | `deploy/app status --env prod` | `action=status` (the address is emailed) |
| Allow / remove an address | `deploy/app allow add 203.0.113.7 --env prod` / `allow remove …` | `action=allow-add` / `allow-remove` with `address` |
| List the allowlist | `deploy/app allow list --env prod` | `action=allow-list` |
| Back up now | `deploy/app backup-now --env prod` | `action=backup-now` |

### Up

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

### Down

`down` stops the web and backend containers, takes a `teardown` backup, and destroys the
instance stack **only if the backup is verified**. Otherwise it stops with exit 4 and destroys
nothing. `--force-without-backup` (`force_without_backup` in GitHub) skips the backup; use it only
for a database that is beyond recovery. Running `down` again when nothing is up is fine.

Backups are also taken every 6 hours while up, and the newest 14 verified ones are kept.

### Status and the address

Each bring-up gets a new public IP; nothing is paid for an address while down. `status` prints
the instance, address, release, uptime, last backup and lock holder, and — because addresses are
masked in GitHub logs — also emails the address when the instance is running.

### Allowlist

The allowlist is the SSM parameter `/cloud-pricing-app/<env>/allowlist`: single addresses only
(`/32` or `/128`), up to 50, kept across down/up cycles, with no expiry. A change applies to a
running instance within a minute or two, without a teardown. Entries never expire, so check the
printed list now and then and remove stale ones. On a mobile network, add the phone's current
address while you need it and remove it afterwards; normally use home Wi-Fi or a VPN back home.

### The lock

`up`, `down`, `allow add|remove` and `backup-now` take `locks/<env>.json` in the backup bucket
for their duration, and GitHub queues runs per environment. If a run died and left the lock, a
later run stops naming the holder; after 2 hours, `--break-lock` removes it.

### Releases and rollback

Merges to `main` are not deployed. Tag a release (`vX.Y.Z`) to build and publish its images;
then run `up` (optionally naming the release). The registries keep the newest 5 releases, so a
rollback can reach back 4 releases; an older one must be re-published first (run **release**
from that tag).

### Logs and the shell

- Logs: CloudWatch Logs group `/cloud-pricing-app/<env>`, one stream per container, kept 14 days.
  The JSON records from the backend arrive as they are.
- Shell: `aws ssm start-session --target <instance-id>` (needs the Session Manager plugin). No
  SSH port exists. On the instance: `cd /opt/app && docker compose ps`, `docker compose logs`.

### Forgotten instance

After 12 hours up, an email says so, and again every 12 hours while it stays up. Nothing is torn
down automatically.

### Updating the server image

```bash
AWS_REGION=us-east-1 deploy/app ami-latest --env prod
```

Put the new ID in `infra/envs/prod.tfvars`, commit, and run `up`. Because the AMI changes, `up`
takes a `redeploy` backup and replaces the instance. From GitHub, the change must be on `main`
first. Run `allow` only after that `up`: it refuses to apply a plan that would replace the
instance.

### Adding an environment (`qa`, `dev`)

1. Copy `infra/envs/qa.tfvars.example` to `qa.tfvars` and `prod.backend.hcl` to
   `qa.backend.hcl`; check the pipeline's `qa` data bucket and read policy names.
2. Add `qa` to the **app** workflow's `environment` choices, create the GitHub environment `qa`
   and its three role secrets.
3. Add `qa` to `RELEASE_ENVIRONMENTS` **before** tagging the release it will run (or re-run
   **release** from an existing tag afterwards).
4. Follow the one-time setup above for `qa`. It gets its own data, backups, TLS root, address and
   roles, and never touches `prod`.

---

## Certificates and devices

Each environment has its own certificate root (EC P-256, 5 years), created on the first `up` and
stored in SSM. Caddy on the instance issues short-lived certificates for the current IP from it,
so a device that trusts the root trusts every bring-up, whatever its address.

Get the root (it is public; the private key never leaves SSM and the instance):

```bash
AWS_REGION=us-east-1 deploy/app cert --env prod --out prod-root.crt
```

- **macOS**: open `prod-root.crt` → Keychain Access adds it to *login* → double-click it →
  *Trust* → *When using this certificate*: **Always Trust**.
- **iOS / iPadOS**: AirDrop or email the `.crt` to the device, open it, install the profile
  (Settings → General → VPN & Device Management), then **Settings → General → About →
  Certificate Trust Settings** → enable full trust for *cloud-pricing-app prod root*.
- **Android**: Settings → Security (or Security & privacy) → *Encryption & credentials* →
  *Install a certificate* → **CA certificate**, and pick the file. Chrome honors user CAs.

The root never changes unless you deliberately run `up --new-root` (needed only if its SSM
parameters are lost while backups exist). `up` warns, and says so in its email, when the root is
within 180 days of expiry; replacing it means `--new-root` and re-trusting every device.

---

## The production stack on a laptop

The same Compose stack the cloud runs, against local data and local backups, with no AWS:

```bash
deploy/app cert local --create              # once: a laptop root in ./.local-tls (trust it)
cp .env.local.example .env.local            # once: set LOCAL_DATA_ROOT
docker compose --env-file .env.local -f compose.yaml -f compose.local.yaml up --build
```

Open `https://localhost:8443` and log in as `Admin` / `admin123` (a fresh local database keeps
the default password; change it in the app). `LOCAL_DATA_ROOT` can be the committed fixture,
`backend/tests/fixtures/pricing_parquet`.

- Back up: `docker compose --env-file .env.local -f compose.yaml -f compose.local.yaml run --rm ops backup --kind manual`
  (files appear in `./.local-backups`).
- Restore check: `… down -v` (wipes the database volume), then `… up`: `db-init` logs
  `"db": "restored"`.
- Health: `… run --rm ops health --wait 60`.

**Seeding the cloud from local data**: with your AWS profile, run the backup with
`BACKUP_URI=s3://<backup-bucket>/prod/db/` (and `AWS_PROFILE`, `AWS_REGION` passed into the
`ops` container); the next cloud `up` from a fresh environment restores it.

The everyday non-packaged workflow (`bin/start_back.sh`, `bin/start_front.sh`) is unchanged; it
only needs `PRICING_DATA_URI` in `backend/.env` (see [configuration](configuration.md#pricing-data)).

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
| 5 | the instance didn't become healthy | the stack is left for diagnosis (logs, Session Manager); run `up` again or `down` |

A failed `up` or `down` can always be re-run; neither needs manual clean-up.

---

## Answered questions

Review findings checked and settled, with their evidence, so they aren't investigated again
(FR-055).

- **Can Caddy read the TLS root that `tls-init` writes mode 0400 as UID 10001?** (PR review,
  2026-10-05.) *Yes.* The pinned `caddy:2` image runs as root (`docker run --entrypoint id caddy:2@…`
  prints `uid=0(root)`), and the packaged stack served HTTPS from these files, including after
  `web` restarts (T063).
- **Must `volume/*` and `network-interface/*` in the `RunInstances` statement carry request-tag
  conditions?** (PR review.) *No.* The statement allows only `ec2:RunInstances`, which can't create
  either on its own; AWS authorizes every resource of a launch, and the instance must carry the
  tags, sit in a tagged subnet and use a verified public image. Requiring request tags on the network
  interface would fail launches, because the AWS provider doesn't reliably tag it.
- **Must the launch permission pin the exact AMI?** (PR review.) *No — a deliberate trade-off.* It
  allows public images from AWS-verified publishers only (`ec2:Owner = amazon` — Canonical's Ubuntu AMIs carry that owner alias, so a condition on Canonical's account ID never matches; found in the first real `up`); the exact AMI is pinned in `<env>.tfvars`. Pinning
  it in IAM would make every AMI update an administrator apply of the base stack, while the deploy
  role can already replace the instance; untrusted or custom images stay refused.
- **Must `ssm:SendCommand`'s document and instance be in one statement?** (PR review.) *No.* IAM
  allows a request when each resource is allowed by some statement. AWS's Run Command guide
  ("Restricting Run Command access based on tags") uses the same two statements — one for the
  document, one for the tagged instance — which also keeps the tag condition off the document.
- **Are `workflow_dispatch` input values visible to anonymous viewers of a public repo?**
  *Open — to be verified with a throwaway run (task T091).* Until then: the address and IP inputs
  are masked in the logs, and allowlist changes can always be made from the laptop instead.
