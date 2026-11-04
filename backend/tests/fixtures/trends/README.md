# Trends fixture (019, T007)

**Synthetic.** Real list prices change too rarely to give a small fixture every case the history
builder must handle (research R11), so the SKUs (`TRD…`) and prices here are invented. They use
the real AWS table schemas, the pipeline storage layout, manifest 1.0 and real
`bytes`/`sha256`/`row_count`, and are read only by tests. Built by
`scripts/build_trends_fixture.py`. Change `PRICES` there and re-run, then update this file.

## Layout

One AWS root, locations `us-east-1` and `us-west-2`, weekly snapshots:

| Week | Snapshot | Revisions |
|---|---|---|
| 1 | 2026-09-07 | 1 |
| 2 | 2026-09-14 | 1 |
| 3 | 2026-09-21 | **1 and 2** (`manifest.json` is revision 2; `revisions/0001.json` is revision 1, whose files are still present) |
| — | 2026-09-28 | **missing** (a gap) |
| 4 | 2026-10-05 | 1 |
| 5 | 2026-10-12 | 1 (`latest.json`) |

Week pairs: 09-07→09-14, 09-14→09-21, 09-21→10-05 (spans the gap), 10-05→10-12.

To test a revision arriving, copy the root, put `revisions/0001.json` in place of
`2026-09-21/manifest.json`, build, then restore revision 2.

## Cases (on-demand price per week; — = SKU absent)

| SKU | Location | Service | 09-07 | 09-14 | 09-21 | 10-05 | 10-12 | Case |
|---|---|---|---|---|---|---|---|---|
| `TRDRISE000000001` | us-east-1 | AmazonEC2 | 0.10 | 0.10 | r1 0.10 / **r2 0.11** | 0.11 | 0.11 | rises (only in revision 2) |
| `TRDFALL000000001` | us-east-1 | AmazonEC2 | 0.20 | 0.18 | 0.18 | 0.18 | 0.18 | falls |
| `TRDBACK000000001` | us-east-1 | AmazonEC2 | 0.30 | 0.30 | 0.33 | 0.30 | 0.30 | rises, then falls back |
| `TRDADDED00000001` | us-east-1 | AmazonS3 | — | — | 0.05 | 0.05 | 0.05 | added |
| `TRDREMOVED000001` | us-east-1 | AmazonS3 | 0.04 | 0.04 | 0.04 | — | — | removed |
| `TRDZERO000000001` | us-east-1 | AmazonEC2 | 0.50 | **0** | 0.50 | 0.50 | 0.50 | zero price: excluded |
| `TRDNULL000000001` | us-east-1 | AmazonEC2 | 0.60 | 0.60 | 0.60 | **null** | 0.60 | missing price: excluded |
| `TRDTIER000000001` | us-east-1 | AWSDataTransfer | 0–1 @ 0; 1–Inf @ 0.09 | same | same | same | 0–1 @ 0; 1–Inf @ **0.085** | free first tier; compared on the first non-zero tier |
| `TRDSTABLE0000001` | us-east-1 | AmazonEC2 | 0.07 | 0.07 | 0.07 | 0.07 | 0.07 | unchanged |
| `TRDSTABLE0000002` | us-east-1 | AmazonS3 | 0.023 | 0.023 | 0.023 | 0.023 | 0.023 | unchanged |
| `TRDW2RISE0000001` | us-west-2 | AmazonEC2 | 0.12 | 0.12 | 0.12 | 0.12 | 0.13 | rises (second location) |
| `TRDW2STABLE00001` | us-west-2 | AmazonEC2 | 0.08 | 0.08 | 0.08 | 0.08 | 0.08 | unchanged |

`TRDRISE000000001` also has a **Reserved** price (1yr, All Upfront) that changes every week
(500, 600, 700, 800, 900). Only on-demand prices count, so it never shows as a change.

## Expected counts per week pair (current revisions)

Per location; `compared` counts SKUs with a valid non-zero price at both ends.

| Pair | Location | compared | unchanged | increased | decreased | added | removed | excluded |
|---|---|---|---|---|---|---|---|---|
| 09-07→09-14 | us-east-1 | 8 | 7 | 0 | 1 (FALL) | 0 | 0 | 1 (ZERO) |
| 09-07→09-14 | us-west-2 | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| 09-14→09-21 | us-east-1 | 8 | 6 | 2 (RISE, BACK) | 0 | 1 (ADDED) | 0 | 1 (ZERO) |
| 09-14→09-21 | us-west-2 | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| 09-21→10-05 (gap) | us-east-1 | 8 | 7 | 0 | 1 (BACK) | 0 | 1 (REMOVED) | 1 (NULL) |
| 09-21→10-05 (gap) | us-west-2 | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| 10-05→10-12 | us-east-1 | 8 | 7 | 0 | 1 (TIER) | 0 | 0 | 1 (NULL) |
| 10-05→10-12 | us-west-2 | 2 | 1 | 1 (W2RISE) | 0 | 0 | 0 | 0 |

With **revision 1** of 2026-09-21 instead, the 09-14→09-21 pair for us-east-1 has 1 increase
(BACK only) and 7 unchanged.

Per service for us-east-1 (compared / increased / decreased / excluded):

| Pair | AmazonEC2 | AmazonS3 | AWSDataTransfer |
|---|---|---|---|
| 09-07→09-14 | 5 / 0 / 1 / 1 | 2 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| 09-14→09-21 | 5 / 2 / 0 / 1 | 2 / 0 / 0 / 0 (1 added) | 1 / 0 / 0 / 0 |
| 09-21→10-05 | 5 / 0 / 1 / 1 | 2 / 0 / 0 / 0 (1 removed) | 1 / 0 / 0 / 0 |
| 10-05→10-12 | 5 / 0 / 0 / 1 | 2 / 0 / 0 / 0 | 1 / 0 / 1 / 0 |

`check_counts.sql` reproduces these numbers straight from the Parquet files (SC-005):

```bash
cd backend
uv run python -c "import duckdb; print(duckdb.sql(open('tests/fixtures/trends/check_counts.sql').read()))"
```

## Expected movers (09-07 → 10-12, all four pairs)

Start price is the price before the SKU's first change in the window, end price the price after
its last change. SKUs that changed and changed back are dropped.

| Direction | SKU | Location | Start | End | % change |
|---|---|---|---|---|---|
| Increase | `TRDRISE000000001` | us-east-1 | 0.10 | 0.11 | +10.00 |
| Increase | `TRDW2RISE0000001` | us-west-2 | 0.12 | 0.13 | +8.33 |
| Decrease | `TRDFALL000000001` | us-east-1 | 0.20 | 0.18 | −10.00 |
| Decrease | `TRDTIER000000001` | us-east-1 | 0.09 | 0.085 | −5.56 (first non-zero tier) |

`TRDBACK000000001` (0.30 → 0.33 → 0.30) is dropped. ADDED, REMOVED, ZERO and NULL never change
between two valid prices, so they are never movers.
