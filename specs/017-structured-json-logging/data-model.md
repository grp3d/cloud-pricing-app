# Data Model: Structured JSON Logging

There are no database changes. The "data" in this feature is the log record, described below,
plus two new settings.

## 1. Log Record

A log record is one JSON object per line on standard output. The `console` format carries the
same fields, rendered as a readable line.

| Field | Type | Always present | Notes |
|---|---|---|---|
| `timestamp` | string | yes | ISO 8601 with UTC offset, e.g. `2026-09-26T21:05:00.123456+00:00` |
| `level` | string | yes | `debug` \| `info` \| `warning` \| `error` \| `critical` |
| `message` | string | yes | The human-readable text, fixed per event type (see contracts/log-format.md) |
| `logger` | string | stdlib records | The logger name, e.g. `uvicorn.error` or `cloud_pricing.active_snapshot` |
| `request_id` | string (32 hex) | during a request | Server-generated, per request |
| `client_request_id` | string (≤ 128 printable) | when the caller sent a valid `X-Request-ID` | Untrusted, informational only |
| `exception` | string | with a traceback | The full traceback text |
| *event fields* | JSON scalar or list | per event | See contracts/log-format.md §2 |

**Rules**:
- Field names are `snake_case`.
- Values that aren't JSON-native (a date, a UUID, a Decimal) are written as strings.
- Headers, bodies, passwords, hashes and tokens are never written as fields.

## 2. Request Context

This is held in per-request context variables, not stored anywhere.

| Field | Set when | Cleared when |
|---|---|---|
| `request_id` | A request starts (middleware) | The next request starts |
| `client_request_id` | A request starts with a valid `X-Request-ID` | The next request starts |

## 3. Settings (additions to `src/config.py`)

| Field | Env var | Type | Default | Validation |
|---|---|---|---|---|
| `log_format` | `LOG_FORMAT` | `"json"` \| `"console"` | `"json"` | Any other value fails startup, naming the setting |
| `log_level` (existing, 016) | `LOG_LEVEL` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` | `INFO` | unchanged |

## 4. Active Snapshot State (addition)

| Field | Type | Purpose |
|---|---|---|
| `logged_waiting` | `dict[str, str]` | Maps snapshot_date to reason for waiting entries already logged, so `pricing snapshot waiting` is logged only when an entry is new or its reason changed. |

## 5. Icon-map generator rows (script)

`build_mapping` returns one row per service code, alongside the printed report:

| Field | Type |
|---|---|
| `service_code` | string |
| `service_name` | string \| null |
| `icon_file` | string \| null (`<stem>.svg`; null when the service falls back) |
| `match_type` | `matched` \| `fuzzy` \| `override` \| `data_transfer` \| `fallback` |

It also returns one row per family override:
`{service_code, product_family, icon_file, match_type: "family_override"}`.
