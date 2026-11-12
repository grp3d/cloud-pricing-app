# Contract: Migration 0009 (GCP and Azure standard architectures)

`backend/src/db/migrations/versions/0009_gcp_azure_standard_architectures.py`, revising
`6c3e9a1b5f08` (0008).

## upgrade()

1. Look up the default Admin (`users.is_default_admin`). If there's none, return without
   inserting anything.
2. For each architecture in `standard_architectures_gcp.json`, then
   `standard_architectures_azure.json`, in file order:
   - Skip it if the Admin owns a non-deleted architecture with the same `name` and `provider`.
   - Otherwise insert the architecture (`is_public = true`), its collections, and their SKU
     selections, including `provider_options` as JSON.
   - Use `clock_timestamp()` for each row, so display order follows file order.
3. Plain SQL only: no ORM imports. It needs no pricing data at run time.

## downgrade()

Delete the SKU selections, collections and architectures that the default Admin owns with
`provider IN ('gcp', 'azure')` and a name from the two seed files.

## Observable behaviour

| Starting state | After `alembic upgrade head` |
|---|---|
| Fresh database | 12 public Admin standard architectures (4 per provider) |
| Database at 0008 with the 4 AWS ones | +8; the AWS ones are unchanged |
| Restored backup taken at 0005 to 0008 | +8 |
| Admin already has a GCP "Serverless Microservices Back-End" | +7 (that one is skipped) |
| Admin has deleted or renamed one of the eight after 0009 ran | No change: the revision doesn't run again |
| No default Admin | No architectures added; the upgrade succeeds |
