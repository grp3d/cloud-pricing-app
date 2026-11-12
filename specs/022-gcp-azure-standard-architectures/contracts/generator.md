# Contract: Standard-architecture generator

`backend/scripts/resolve_standard_architectures.py` is an internal developer command. It runs
only when the designs or the pricing data need regenerating.

## Command

```bash
cd backend
uv run python scripts/resolve_standard_architectures.py \
    [--provider aws|gcp|azure]        # default: aws (unchanged behaviour)
    [--source ../docs/brief/common_aws_architectures.md]
    [--data-uri file:///…/_DATA-PIPELINE]   # default: PRICING_DATA_URI
```

- `--provider` selects the rules module (`match_rules.py`, `match_rules_gcp.py` or
  `match_rules_azure.py`) and that provider's latest usable snapshot. The snapshot can be
  pinned with `ACTIVE_SNAPSHOT_DATE`, for AWS only, as today.
- `--data-uri` must be a local pipeline storage root.

## Outputs (written to `backend/src/db/seed/`)

| Provider | Seed | Report |
|---|---|---|
| aws | `standard_architectures.json` (unchanged) | `standard_architectures_report.md` (unchanged) |
| gcp | `standard_architectures_gcp.json` | `standard_architectures_gcp_report.md` |
| azure | `standard_architectures_azure.json` | `standard_architectures_azure_report.md` |

- The seed is in the architecture export format, format version 1 (see data-model §2).
- The GCP and Azure reports have these parts, in order:
  1. The title, "do not edit by hand", the provider and the pricing snapshot date.
  2. One section per architecture, in reference order. Each has a matches table with these
     columns: `AWS component | Figure | Region | Service | SKU | Unit | Quantity | Tiered | Size | Note`.
  3. A **Left out** table per section: `AWS component | Figure | Reason`.

## Exit codes

| Code | When |
|---|---|
| 0 | Both files written. Stdout: `<provider> snapshot <date>: <n> entries matched, <m> figures left out -> <dir>` |
| 1 | A chosen SKU's unit is unrecognized, or an architecture resolved no priced entries at all. Nothing is written. |
| 2 (`SystemExit` message) | No data URI, a non-local store, or no usable snapshot for the provider. This includes a snapshot missing a region the rules need. |

## Guarantees

- **Deterministic:** the same rules, reference and snapshot give byte-identical output.
- **Complete:** every figure of every reference component appears exactly once per provider,
  either matched or left out.
- **Honest:** nothing is approximated. A figure without a matching SKU is left out with a
  reason (Constitution Principle I).
