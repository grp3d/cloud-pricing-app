# AWS pricing fixture

Snapshot `2026-09-24`, revision 1, built by `scripts/build_test_pricing_fixture.py` from the local
pipeline root. Rows are copied verbatim from the source snapshot and never edited.

## Tiered rows (019, T006, research R8)

Added to `us-west-2` (`product_dim`, `product_attribute`, `price_fact`) by appending the source
rows for one SKU to the existing files, so every existing row keeps its position. Some lookups
take the first of several rows, which is why the fixture is not simply rebuilt: a rebuild
reorders `product_dim` and `product_attribute`. The SKU is also in the builder's `SEED_SKUS`,
so any later rebuild includes it.

| SKU | Service | What | Unit | Tiers (`begin_range`–`end_range` @ USD per GB) |
|---|---|---|---|---|
| `5M4327XEUKBBTWAT` | `AWSDataTransfer` | AWS Outbound, US West (Oregon) → External | GB | 0–10240 @ 0.09; 10240–51200 @ 0.085; 51200–153600 @ 0.07; 153600–Inf @ 0.05 |

Expected (T013): 20,480 GB in a month costs 10,240 × 0.09 + 10,240 × 0.085 = **$1,792.00**.

Tiered SKUs already in the fixture before 019, also in `us-west-2`:

| SKU | Tiers |
|---|---|
| `Z3FQZG73HYSPVABR` | 0–51200 @ 0.023; 51200–512000 @ 0.022; 512000–Inf @ 0.021 (S3 storage, GB-Mo) |
| `35NUEJDPRHV4T4PW` | 0–25000000000 @ 2e-07; 25000000000–100000000000 @ 1.6e-07; 100000000000–Inf @ 1.2e-07 |
