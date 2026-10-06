# Backend for this repository's prod stacks, in the account's shared state bucket under app/prod/
# (FR-056). Pass the stack's key separately:
#   tofu init -backend-config=../envs/prod.backend.hcl -backend-config="key=app/prod/<stack>.tfstate"
bucket       = "cloud-pricing-shared-tfstate-g08a9i"
region       = "us-east-1"
encrypt      = true
use_lockfile = true
