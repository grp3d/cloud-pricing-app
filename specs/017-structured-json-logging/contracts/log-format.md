# Contract: Log Record Format and Event Catalog

Anything that reads the backend's logs (a log shipper, a search tool, or a person using `jq`) can
rely on this contract.

## 1. Record shape

With the default `LOG_FORMAT=json`, each record is one line on standard output, holding exactly
one JSON object:

```json
{"timestamp": "2026-09-26T21:05:00.123456+00:00", "level": "info", "message": "request completed",
 "logger": "cloud_pricing", "request_id": "6f1c0e2a9b8d4c7e8f0a1b2c3d4e5f60",
 "method": "GET", "path": "/architectures", "status_code": 200, "duration_ms": 12.4}
```

(The example is wrapped here for readability. A real record is always a single line.)

**Guarantees**:

1. **Always-present fields**: `timestamp`, `level` and `message` appear on every record.
   - `timestamp` is ISO 8601 with a `+00:00` offset.
   - `level` is one of `debug`, `info`, `warning`, `error` or `critical`.
2. **Tracebacks** are carried in a string field named `exception`, never on extra lines.
3. **Request fields**:
   - `request_id` is present on every record logged while handling an HTTP request.
   - `client_request_id` is present only when the caller sent a valid `X-Request-ID`
     (see §3).
4. **Level threshold**: records below `LOG_LEVEL` are not written.
5. **Excluded content**: no record contains request or response headers (other than
   `client_request_id`), bodies, query strings, passwords, password hashes or bearer tokens.
6. **Console format**: with `LOG_FORMAT=console`, the same fields are rendered as one colored,
   human-readable line. This format is not machine-readable and is intended for local
   development only.

## 2. Event catalog

Messages are fixed strings, so you can filter with `message == "..."`. All events listed below
come from logger names under `cloud_pricing`.

| `message` | `level` | Detail fields |
|---|---|---|
| `request completed` | info | `method`, `path`, `status_code` (int), `duration_ms` (float) |
| `pricing data unavailable` | error | `path`, `error` |
| `active pricing snapshot selected` | info | `snapshot_date` (YYYY-MM-DD \| null), `pinned` (bool) |
| `active pricing snapshot changed` | info | `snapshot_date`, `previous_snapshot_date`, `pinned` |
| `pricing snapshot waiting` | info | `snapshot_date`, `reason` |
| `pricing snapshot missing regions` | warning | `snapshot_date`, `previous_snapshot_date`, `regions` (list[str]) |
| `pricing snapshot check failed` | error | `error`, `exception` when a traceback is available |
| `icon coverage analyzed` | info | `snapshot_date`, `missing_icon_count` (int), `new_service_codes` (list[str]) |
| `service has no icon` | debug | `snapshot_date`, `service_code`, `service_name`, `is_new` (bool) |
| `icon coverage analysis failed` | error | `exception` |
| `service moved` | info | `sku_selection_id`, `sku`, `service_code`, `source_collection_id`, `target_collection_id` |
| `service move refused` | warning | the same fields as `service moved`, plus `reason` (`not_movable` \| `region_mismatch`) |

**Records from other loggers**: records from the web server (`uvicorn`, `uvicorn.error`) and from
libraries have the same always-present fields, plus `logger`. Their `message` text is whatever
that library writes.

## 3. `X-Request-ID` HTTP header

- **Response**: every response carries `X-Request-ID: <request_id>`. This is the server-generated
  value, 32 lowercase hex characters. The header is listed in CORS `Access-Control-Expose-Headers`.
- **Request (optional)**: a caller may send `X-Request-ID`.
  - If the value is 1–128 printable ASCII characters (`0x20`–`0x7E`), it is logged as
    `client_request_id`.
  - Otherwise it is silently ignored.
  - In either case the value is never echoed back and never replaces `request_id`.

## 4. Icon-map generator: `--log-file`

```text
uv run python scripts/generate_aws_service_icon_map.py --icons <dir> [--log-file PATH]
```

- **Without `--log-file`**: only the existing readable report is printed to standard output.
  No JSON is written.
- **With `--log-file PATH`**: the report is still printed, and in addition `PATH` is created or
  overwritten with one JSON record per line, using the same record shape as §1:

| `message` | Fields |
|---|---|
| `service icon matched` | `service_code`, `service_name`, `icon_file` (null for fallback), `match_type` (`matched` \| `fuzzy` \| `override` \| `data_transfer` \| `fallback`) |
| `family icon override` | `service_code`, `product_family`, `icon_file`, `match_type` = `family_override` |
| `icon copied` | `icon_file` |
