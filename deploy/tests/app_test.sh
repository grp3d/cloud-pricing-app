#!/usr/bin/env bash
# Tests for deploy/app (018-app-cloud-deployment; contracts/app-cli.md). Plain bash, no network:
# fake `aws` and `tofu` (deploy/tests/fakes) record their calls and answer from files, so each
# test sets up a scenario, runs the real script, and checks its exit code, output and calls.
#
#   bash deploy/tests/app_test.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../app"
FAKES="$HERE/fakes"
PASSED=0
FAILED=0
CURRENT=""

ROOT_CERT_DIR="$(mktemp -d)"
openssl ecparam -name prime256v1 -genkey -noout -out "$ROOT_CERT_DIR/root.key" 2>/dev/null
openssl req -x509 -new -key "$ROOT_CERT_DIR/root.key" -sha256 -days 1825 -subj "/CN=test root" \
  -out "$ROOT_CERT_DIR/root.crt" 2>/dev/null
openssl req -x509 -new -key "$ROOT_CERT_DIR/root.key" -sha256 -days 30 -subj "/CN=old root" \
  -out "$ROOT_CERT_DIR/expiring.crt" 2>/dev/null

# --- Harness ------------------------------------------------------------------------------------

setup_case() {
  CURRENT="$1"
  CASE="$(mktemp -d)"
  REPO="$CASE/repo"
  FAKE_DIR="$CASE/fake"
  mkdir -p "$REPO/deploy" "$REPO/infra/envs" "$REPO/infra/instance" "$REPO/infra/base" "$FAKE_DIR" "$CASE/home/.aws"
  cp "$SCRIPT" "$REPO/deploy/app"
  cat >"$REPO/infra/envs/prod.tfvars" <<'TFVARS'
environment = "prod"
aws_region  = "us-east-1"
ami_id = "ami-0123456789abcdef0"
TFVARS
  cat >"$REPO/infra/envs/prod.backend.hcl" <<'HCL'
bucket       = "cloud-pricing-shared-tfstate-test01"
region       = "us-east-1"
HCL
  printf '[default]\nregion = eu-west-1\n' >"$CASE/home/.aws/config"
  : >"$FAKE_DIR/calls"

  fake s3.cp.base '{"outputs": {
    "backup_bucket": {"value": "cloud-pricing-app-backups-prod-test01"},
    "allowlist_parameter": {"value": "/cloud-pricing-app/prod/allowlist"},
    "repository_names": {"value": {"backend": "cloud-pricing-app-backend-prod", "web": "cloud-pricing-app-web-prod"}},
    "repository_urls": {"value": {"backend": "r/backend", "web": "r/web"}}}}'
  fake sts.get-caller-identity '{"Account": "123456789012", "Arn": "arn:aws:sts::123456789012:assumed-role/x/y"}'
  fake ec2.describe-images 'ami-0123456789abcdef0'
  fake ec2.describe-instances '[]'
  parameter /cloud-pricing-app/prod/owner-password 'secret'
  parameter /cloud-pricing-app/prod/allowlist '203.0.113.5/32'
  parameter /cloud-pricing-app/prod/tls/root-cert "$(cat "$ROOT_CERT_DIR/root.crt")"
  fake ecr.describe-images '[{"tags": ["v1.0.0"], "digest": "sha256:aaa"}, {"tags": ["v1.2.0"], "digest": "sha256:bbb"}, {"tags": ["v1.10.0"], "digest": "sha256:ccc"}]'
  fake s3api.list-objects-v2 '0'
  fake ssm.send-command 'cmd-1'
  fake ssm.describe-instance-information 'Online'
  fake tofu.output.json '{"instance_id": {"value": "i-new"}, "public_ip": {"value": "198.51.100.20"}}'
  invocation Success '{"healthy": true, "db": "restored", "pricing": "ok", "pricing_reason": null, "release": "v1.10.0"}'
}

fake() { printf '%s' "$2" >"$FAKE_DIR/$1"; }
parameter() { printf '%s' "$2" >"$FAKE_DIR/ssm.get-parameter.${1//\//_}"; }
invocation() {  # invocation <status> <last stdout line>
  jq -n --arg s "$1" --arg out "$2" \
    '{Status: $s, StandardOutputContent: ("some log line\n" + $out + "\n"), StandardErrorContent: "stderr tail"}' \
    >"$FAKE_DIR/ssm.get-command-invocation"
}
queue_invocation() {  # queue_invocation <n> <status> <last stdout line>
  jq -n --arg s "$2" --arg out "$3" '{Status: $s, StandardOutputContent: ($out + "\n"), StandardErrorContent: ""}' \
    >"$FAKE_DIR/ssm.get-command-invocation.q$1"
}
running_instance() {
  fake ec2.describe-instances '[{"InstanceId": "i-old", "State": {"Name": "running"}, "PublicIpAddress": "203.0.113.7", "LaunchTime": "2026-10-02T10:00:00+00:00", "Tags": [{"Key": "release", "Value": "v1.0.0"}]}]'
}

run_app() {
  (cd "$REPO" && env -i PATH="$FAKES:$PATH" HOME="$CASE/home" FAKE_DIR="$FAKE_DIR" \
    APP_POLL_SECONDS=0 ${EXTRA_ENV[@]+"${EXTRA_ENV[@]}"} ./deploy/app "$@") >"$CASE/out" 2>"$CASE/err"
  RC=$?
}
EXTRA_ENV=(AWS_REGION=us-east-1)

fail() {
  FAILED=$((FAILED + 1))
  printf 'FAIL %s: %s\n' "$CURRENT" "$*"
  printf '  stderr: %s\n' "$(tail -n 5 "$CASE/err" | tr '\n' '|')"
}
pass() { PASSED=$((PASSED + 1)); printf 'ok   %s\n' "$CURRENT"; }

check() {  # check <description> <command...>; the case passes only if every check passes
  local what="$1"; shift
  if ! "$@"; then CASE_OK=0; fail "$what"; fi
}
begin() { setup_case "$1"; CASE_OK=1; EXTRA_ENV=(AWS_REGION=us-east-1); }
end() { if [[ $CASE_OK == 1 ]]; then pass; fi; rm -rf "$CASE"; }

exit_is() { [[ "$RC" == "$1" ]] || { echo "  exit $RC, wanted $1"; return 1; }; }
stderr_has() { grep -qF -- "$1" "$CASE/err"; }
stdout_has() { grep -qF -- "$1" "$CASE/out"; }
called() { grep -qE -- "$1" "$FAKE_DIR/calls"; }
not_called() { ! grep -qE -- "$1" "$FAKE_DIR/calls"; }
line_of() { grep -nE -- "$1" "$FAKE_DIR/calls" | head -n 1 | cut -d: -f1; }
last_line_of() { grep -nE -- "$1" "$FAKE_DIR/calls" | tail -n 1 | cut -d: -f1; }
called_before() {  # called_before <a> <b>: the first <a> comes before the last <b>
  local a b
  a="$(line_of "$1")"; b="$(last_line_of "$2")"
  [[ -n "$a" && -n "$b" && "$a" -lt "$b" ]]
}

# --- Arguments and environment (T032) ---------------------------------------------------------

begin "missing --env is a usage error"
run_app status
check "exit 2" exit_is 2
check "names --env" stderr_has "--env is required"
end

begin "missing AWS_REGION is a usage error even with a region in ~/.aws/config"
EXTRA_ENV=(APP_ENV=prod)
run_app status
check "exit 2" exit_is 2
check "names AWS_REGION" stderr_has "AWS_REGION is required"
check "no AWS call" not_called '^(ec2|ssm|s3)'
end

begin "AWS_REGION must match the env's tfvars"
EXTRA_ENV=(AWS_REGION=eu-west-1)
run_app status --env prod
check "exit 2" exit_is 2
end

begin "a missing base stack is a precondition error"
rm "$FAKE_DIR/s3.cp.base"
run_app up --env prod
check "exit 3" exit_is 3
check "points at the one-time setup" stderr_has "one-time setup"
end

# --- Lock (T032) --------------------------------------------------------------------------------

begin "a held lock is exit 3 and names the holder"
fake s3api.put-object.fail 'An error occurred (PreconditionFailed) when calling the PutObject operation: At least one of the pre-conditions you specified did not hold'
fake s3.cp.lock "{\"action\": \"down\", \"by\": \"github:someone\", \"started_at\": $(date -u +%s), \"run_url\": \"\"}"
run_app backup-now --env prod
check "exit 3" exit_is 3
check "names the holder" stderr_has "down by github:someone"
check "does not delete someone else's lock" not_called 's3api delete-object'
end

begin "--break-lock breaks only an old lock"
fake s3api.put-object.q1 'FAIL:An error occurred (PreconditionFailed) when calling the PutObject operation'
fake s3.cp.lock '{"action": "up", "by": "laptop", "started_at": 1000, "run_url": ""}'
running_instance
invocation Success '{"backup_id": "x", "verified": true, "bytes": 1, "deleted": []}'
run_app backup-now --env prod --break-lock
check "exit 0" exit_is 0
check "deleted the stale lock, then took it" called_before 's3api delete-object .*locks/prod.json' 's3api put-object .*locks/prod.json'
end

begin "the lock is released when a later step fails"
fake ecr.describe-images '[]'
run_app up --env prod
check "exit 3" exit_is 3
check "lock taken" called 's3api put-object .*--key locks/prod.json'
check "lock released" called 's3api delete-object .*--key locks/prod.json'
end

# --- SSM (T032) ---------------------------------------------------------------------------------

for status in Failed Cancelled TimedOut; do
  begin "ssm_run fails on $status"
  running_instance
  invocation "$status" '{"verified": true}'
  run_app backup-now --env prod
  check "exit 4" exit_is 4
  check "reports the status" stderr_has "ended with status $status"
  end
done

# --- Masking and status (T032, FR-038, FR-050) -------------------------------------------------

begin "addresses and the account are masked in GitHub"
running_instance
invocation Success '{"backups": [{"id": "20261002T000000Z-scheduled-v1.0.0", "verified": true}]}'
EXTRA_ENV=(AWS_REGION=us-east-1 GITHUB_ACTIONS=true)
run_app status --env prod
check "exit 0" exit_is 0
check "masks the address" stdout_has "::add-mask::203.0.113.7"
end

begin "status of a running instance also emails the address"
running_instance
invocation Success '{"published": true}'
run_app status --env prod
check "exit 0" exit_is 0
check "sends ops notify" called 'ssm send-command .*ops notify'
check "shows the address" stderr_has "https://203.0.113.7"
end

begin "status with nothing running sends no command"
run_app status --env prod
check "exit 0" exit_is 0
check "no SSM command" not_called 'ssm send-command'
check "reads backups from S3" called 's3api list-objects-v2'
end

# --- up (T052, T068) ----------------------------------------------------------------------------

begin "up picks the highest semver release present in both repositories"
fake ecr.describe-images.q1 '[{"tags": ["v1.2.0"], "digest": "sha256:b12"}, {"tags": ["v1.10.0"], "digest": "sha256:b110"}, {"tags": ["v2.0.0"], "digest": "sha256:b200"}]'
fake ecr.describe-images.q2 '[{"tags": ["v1.2.0"], "digest": "sha256:w12"}, {"tags": ["v1.10.0"], "digest": "sha256:w110"}]'
run_app up --env prod
check "exit 0" exit_is 0
check "deploys v1.10.0 (not v2.0.0, missing from web; not v1.2.0)" called 'tofu plan .*release=v1.10.0'
check "by digest" called 'tofu plan .*backend_digest=sha256:b110 .*web_digest=sha256:w110'
check "reports the address" stdout_has "https://198.51.100.20"
check "applies the saved plan" called 'tofu apply .*instance.plan'
check "never -auto-approve on up" not_called 'tofu apply .*-auto-approve'
end

begin "up with a named release missing from the registry fails before tofu"
run_app up --env prod --release v9.9.9
check "exit 3" exit_is 3
check "says why" stderr_has "release v9.9.9 is not in this environment's registry"
check "no tofu plan" not_called '^tofu plan'
end

begin "a malformed release is a usage error"
run_app up --env prod --release latest
check "exit 2" exit_is 2
end

begin "a missing TLS root with no backups is created"
rm "$FAKE_DIR/ssm.get-parameter._cloud-pricing-app_prod_tls_root-cert"
run_app up --env prod
check "exit 0" exit_is 0
check "stores the key as SecureString" called 'ssm put-parameter --name /cloud-pricing-app/prod/tls/root-key --type SecureString --value file://'
check "stores the cert" called 'ssm put-parameter --name /cloud-pricing-app/prod/tls/root-cert --type String'
check "tells the owner" stderr_has "NEW ROOT CREATED"
check "never prints the key" bash -c "! grep -q 'PRIVATE KEY' '$CASE/out' '$CASE/err' '$FAKE_DIR/calls'"
end

begin "a missing TLS root with backups needs --new-root"
rm "$FAKE_DIR/ssm.get-parameter._cloud-pricing-app_prod_tls_root-cert"
fake s3api.list-objects-v2 '3'
run_app up --env prod
check "exit 3" exit_is 3
check "mentions --new-root" stderr_has "--new-root"
check "creates nothing" not_called 'ssm put-parameter'
end

begin "a TLS root close to expiry warns but is kept"
parameter /cloud-pricing-app/prod/tls/root-cert "$(cat "$ROOT_CERT_DIR/expiring.crt")"
run_app up --env prod
check "exit 0" exit_is 0
check "warns" stderr_has "TLS root expires on"
check "does not replace it" not_called 'ssm put-parameter'
check "puts it in the notice" called "ssm send-command .*ops notify.*'[^']*TLS root expires on"
end

begin "a plan that leaves the running instance alone takes no backup"
running_instance
run_app up --env prod
check "exit 0" exit_is 0
check "no redeploy backup" not_called 'backup --kind redeploy'
end

for cause in release ami db_init_args; do
  begin "a plan that replaces the running instance ($cause) backs up first"
  running_instance
  fake tofu.show.json '{"resource_changes": [{"type": "aws_instance", "change": {"actions": ["delete", "create"]}}]}'
  queue_invocation 1 Success '{"backup_id": "20261003T000000Z-redeploy-v1.0.0", "verified": true}'
  if [[ $cause == db_init_args ]]; then set -- --backup 20261001T000000Z-scheduled-v1.0.0; else set --; fi
  run_app up --env prod "$@"
  check "exit 0" exit_is 0
  check "backup before apply" called_before 'backup --kind redeploy' '^tofu apply'
  end
done

begin "a failed redeploy backup applies nothing"
running_instance
fake tofu.show.json '{"resource_changes": [{"type": "aws_instance", "change": {"actions": ["create", "delete"]}}]}'
queue_invocation 1 Success '{"backup_id": "x", "verified": false}'
run_app up --env prod
check "exit 4" exit_is 4
check "no apply" not_called '^tofu apply'
end

begin "an unhealthy result is exit 5"
invocation Success '{"healthy": false, "db": "failed", "error": "db-init failed"}'
run_app up --env prod
check "exit 5" exit_is 5
end

begin "pricing unavailable is success with a warning"
invocation Success '{"healthy": true, "db": "fresh", "pricing": "unavailable", "pricing_reason": "no snapshot available", "release": "v1.10.0"}'
run_app up --env prod
check "exit 0" exit_is 0
check "warns" stdout_has "pricing is unavailable: no snapshot available"
end

begin "first-deploy guard: missing owner password"
rm "$FAKE_DIR/ssm.get-parameter._cloud-pricing-app_prod_owner-password"
run_app up --env prod
check "exit 3" exit_is 3
check "names the parameter" stderr_has "/cloud-pricing-app/prod/owner-password"
end

begin "first-deploy guard: AMI placeholder"
sed -i.bak 's/ami-0123456789abcdef0/REPLACE-ME/' "$REPO/infra/envs/prod.tfvars"
run_app up --env prod
check "exit 3" exit_is 3
check "says how to fix" stderr_has "ami-latest"
end

begin "first-deploy guard: empty allowlist only warns"
parameter /cloud-pricing-app/prod/allowlist 'none'
run_app up --env prod
check "exit 0" exit_is 0
check "warns" stderr_has "nobody can reach the app"
end

# --- down (T064) --------------------------------------------------------------------------------

begin "down with nothing deployed succeeds without SSM or destroy"
run_app down --env prod
check "exit 0" exit_is 0
check "no SSM" not_called 'ssm send-command'
check "no destroy" not_called 'tofu destroy'
end

begin "down with leftover resources but no instance destroys them"
fake tofu.state 'aws_vpc.main'
run_app down --env prod
check "exit 0" exit_is 0
check "no SSM" not_called 'ssm send-command'
check "destroys" called 'tofu destroy'
end

begin "down stops if the backup is not verified"
running_instance
invocation Success '{"backup_id": "x", "verified": false}'
run_app down --env prod
check "exit 4" exit_is 4
check "no destroy" not_called 'tofu destroy'
end

begin "down stops if the SSM backup command fails"
running_instance
invocation Failed ''
run_app down --env prod
check "exit 4" exit_is 4
check "no destroy" not_called 'tofu destroy'
end

begin "down --force-without-backup destroys and warns"
running_instance
fake ec2.describe-instances.q1 '[{"InstanceId": "i-old", "State": {"Name": "running"}, "Tags": []}]'
fake ec2.describe-instances.q2 '[]'
run_app down --env prod --force-without-backup
check "exit 0" exit_is 0
check "no backup" not_called 'backup --kind teardown'
check "destroys" called 'tofu destroy'
check "warns" stderr_has "WITHOUT a final backup"
end

begin "down: lock, stop and back up, destroy, confirm, unlock — in that order"
fake ec2.describe-instances.q1 '[{"InstanceId": "i-old", "State": {"Name": "running"}, "Tags": []}]'
fake ec2.describe-instances.q2 '[]'
invocation Success '{"backup_id": "20261003T000000Z-teardown-v1.0.0", "verified": true}'
run_app down --env prod
check "exit 0" exit_is 0
check "lock before backup" called_before 's3api put-object .*locks/prod.json' 'ssm send-command'
check "stop web and backend, then teardown backup" called 'ssm send-command .*stop web backend.*backup --kind teardown'
check "backup before destroy" called_before 'ssm send-command' '^tofu destroy'
check "confirm after destroy" called_before '^tofu destroy' 'ec2 describe-instances'
check "unlock last" called 's3api delete-object .*locks/prod.json'
end

begin "down fails if a tagged instance survives destroy"
running_instance
invocation Success '{"backup_id": "x", "verified": true}'
run_app down --env prod
check "fails" bash -c "[[ $RC != 0 ]]"
check "says so" stderr_has "still exists after destroy"
end

# --- allow (T080) -------------------------------------------------------------------------------

begin "allow add stores IPv4 as /32 and prints the list"
run_app allow add 198.51.100.9 --env prod
check "exit 0" exit_is 0
check "writes both entries" called 'ssm put-parameter --name /cloud-pricing-app/prod/allowlist --type StringList --value 203.0.113.5/32,198.51.100.9/32 --overwrite'
check "prints the list" stderr_has "198.51.100.9/32"
check "takes the lock" called 's3api put-object .*locks/prod.json'
end

begin "allow add stores IPv6 as /128"
run_app allow add 2001:DB8::1 --env prod
check "exit 0" exit_is 0
check "lowercase /128" called '--value 203.0.113.5/32,2001:db8::1/128'
end

for bad in 10.0.0.0/8 example.com 300.1.1.1 ""; do
  begin "allow add rejects '$bad'"
  run_app allow add "$bad" --env prod
  check "exit 2" exit_is 2
  check "no write" not_called 'ssm put-parameter'
  end
done

begin "allow add of an existing entry is a no-op"
run_app allow add 203.0.113.5 --env prod
check "exit 0" exit_is 0
check "no write" not_called 'ssm put-parameter'
check "says so" stderr_has "already allowed"
end

begin "allow remove of a missing entry is a no-op with a message"
run_app allow remove 198.51.100.200 --env prod
check "exit 0" exit_is 0
check "no write" not_called 'ssm put-parameter'
check "says so" stderr_has "nothing to remove"
end

begin "allow remove of the last entry restores the placeholder"
run_app allow remove 203.0.113.5 --env prod
check "exit 0" exit_is 0
check "writes none" called '--value none --overwrite'
check "says nobody can reach it" stderr_has "nobody can reach the app"
end

begin "allow add over 50 entries is refused"
parameter /cloud-pricing-app/prod/allowlist "$(for i in $(seq 1 50); do printf '10.0.0.%s/32,' "$i"; done | sed 's/,$//')"
run_app allow add 198.51.100.9 --env prod
check "exit 2" exit_is 2
end

begin "allow while down changes the parameter only"
run_app allow add 198.51.100.9 --env prod
check "no tofu plan" not_called '^tofu plan'
end

begin "allow while up re-applies with the running instance's own values"
running_instance
fake tofu.output.json '{"instance_id": {"value": "i-old"}, "release": {"value": "v1.0.0"}, "ami_id": {"value": "ami-00000000000000000"}, "backend_digest": {"value": "sha256:b"}, "web_digest": {"value": "sha256:w"}, "db_init_args": {"value": ""}}'
run_app allow add 198.51.100.9 --env prod
check "exit 0" exit_is 0
check "plans with the running values" called 'tofu plan .*release=v1.0.0 .*backend_digest=sha256:b .*web_digest=sha256:w .*ami_id=ami-00000000000000000'
check "applies the saved plan" called 'tofu apply .*instance.plan'
end

begin "allow refuses a plan that would replace the instance and restores the list"
running_instance
fake tofu.output.json '{"release": {"value": "v1.0.0"}, "ami_id": {"value": "ami-00000000000000000"}, "backend_digest": {"value": "sha256:b"}, "web_digest": {"value": "sha256:w"}, "db_init_args": {"value": ""}}'
fake tofu.show.json '{"resource_changes": [{"type": "aws_instance", "change": {"actions": ["delete", "create"]}}]}'
run_app allow add 198.51.100.9 --env prod
check "exit 3" exit_is 3
check "says run up" stderr_has "Run deploy/app up instead"
check "no apply" not_called '^tofu apply'
check "restores the previous value" called '--value 203.0.113.5/32 --overwrite'
end

# --- cert and ami-latest (T081, T082) ---------------------------------------------------------

begin "cert --out saves the public root"
run_app cert --env prod --out "$CASE/prod-root.crt"
check "exit 0" exit_is 0
check "writes the cert" grep -q "BEGIN CERTIFICATE" "$CASE/prod-root.crt"
end

begin "cert local --create makes a laptop root without AWS"
EXTRA_ENV=()
run_app cert local --create
check "exit 0" exit_is 0
check "cert" test -f "$REPO/.local-tls/root.crt"
check "key is private" bash -c "[[ \$(stat -c %a '$REPO/.local-tls/root.key' 2>/dev/null || stat -f %Lp '$REPO/.local-tls/root.key') == 600 ]]"
check "no AWS call" not_called '^(ssm|s3|ec2|sts)'
end

begin "ami-latest prints Canonical's current arm64 AMI"
parameter /aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id 'ami-0fedcba9876543210'
run_app ami-latest --env prod
check "exit 0" exit_is 0
check "prints it" stdout_has "ami-0fedcba9876543210"
end

rm -rf "$ROOT_CERT_DIR"
printf '\n%d passed, %d failed\n' "$PASSED" "$FAILED"
[[ $FAILED -eq 0 ]]
