# Phase 0 Research: Structured JSON Logging

All decisions below are based on the current backend: `src/main.py`, which calls
`logging.basicConfig` and has a request middleware, and `src/pricing_data/active_snapshot.py`.
The Uvicorn logging defaults were read from `uvicorn.config.LOGGING_CONFIG`, and the structlog
release is 26.1.0 (Python ≥ 3.10, MIT/Apache-2.0). The spec has no open questions.

---

## 1. Library and pipeline

**Decision**: add `structlog>=26.1` to `backend/pyproject.toml`. One module,
`backend/src/logging_config.py`, exposes
`configure_logging(level: str, fmt: Literal["json","console"], stream=sys.stdout)`.

It builds a shared structlog processor chain:

1. `structlog.contextvars.merge_contextvars` adds the request-scoped fields (`request_id`,
   `client_request_id`).
2. `structlog.stdlib.add_log_level` produces a lower-case `level` (FR-002).
3. `structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp")` produces an
   ISO 8601 UTC timestamp (FR-002).
4. `structlog.processors.EventRenamer("message")` renames structlog's `event` key to `message`
   (FR-002).
5. `structlog.processors.format_exc_info` puts the traceback text in an `exception` field
   (FR-004).
6. The renderer depends on the format:
   - `json`: `structlog.processors.JSONRenderer(default=str)`, which writes a non-JSON value as
     text (FR-011).
   - `console`: `structlog.dev.ConsoleRenderer(colors=True)` (FR-001a).

**Both structlog and stdlib loggers render the same way**: the chain is installed on a single
root `logging.StreamHandler` through `structlog.stdlib.ProcessorFormatter`, with the shared chain
as `foreign_pre_chain`. So records from structlog loggers and from plain `logging` loggers (the
web server, SQLAlchemy, asyncio) come out in the same format (FR-003). structlog is configured
with `structlog.stdlib.LoggerFactory()` and `wrap_logger`, and its last processor is
`ProcessorFormatter.wrap_for_formatter`.

**Rationale**: this is structlog's documented setup for integrating with the standard library.
There's one handler and one formatter, so every log line in the process has the same shape.

**Alternatives considered**:
- *structlog's own PrintLogger with no stdlib bridge*: rejected. Uvicorn and SQLAlchemy log
  through the standard library and would stay as unstructured text.
- *python-json-logger*: rejected. You asked for structlog.

## 2. Web server (Uvicorn) logs

**Finding**: Uvicorn applies its own `LOGGING_CONFIG` when it starts:
- `uvicorn` has `propagate=False` and its own handler;
- `uvicorn.error` propagates up to `uvicorn`;
- `uvicorn.access` has `propagate=False` and its own handler.

Its lines therefore bypass any root handler.

**Decision**: `configure_logging` removes the handlers from the `uvicorn`, `uvicorn.error` and
`uvicorn.access` loggers and sets them to propagate, so their records reach the root JSON handler
(FR-003).

It also sets `uvicorn.access` to `WARNING`. The app's own request log (§4) replaces Uvicorn's
access line: it has richer fields (`duration_ms`, `request_id`) and never logs query strings or
headers (FR-006). Otherwise every request would produce two lines.

`configure_logging` runs when `src/main.py` is imported, which happens after Uvicorn has applied
its config, so it wins. It is idempotent (it replaces the root handlers), so tests and `--reload`
don't stack up duplicate handlers.

## 3. Settings

**Decision**: add `log_format: Literal["json", "console"] = "json"` to `Settings`. An invalid
value fails validation and stops startup, naming the setting (FR-001a). `log_level` already exists
(016) and is reused (FR-005). Both are documented in `docs/configuration.md` and
`backend/.env.example`.

## 4. Request ID and request log

**Decision**: replace the existing `log_requests` middleware in `src/main.py` with one that does
the following:

1. Calls `structlog.contextvars.clear_contextvars()`, then binds
   `request_id = uuid4().hex` (FR-006a).
2. Reads `X-Request-ID`. If it matches `^[\x20-\x7E]{1,128}$` (printable ASCII, at most 128
   characters), binds it as `client_request_id`; otherwise ignores it (FR-006b).
3. Times the call with `time.perf_counter()` and logs `request completed` at `info` with
   `method`, `path` (the path only, no query string), `status_code` and `duration_ms` (a number,
   rounded to 0.1 ms) (FR-006).
4. Sets the `X-Request-ID` response header to the server's `request_id`, never the client's.
5. Adds `X-Request-ID` to the CORS middleware's `expose_headers`, so the browser can read it for
   future use.

**Why this reaches every line of the request**: context variables are per task, and FastAPI runs
each request in its own task, so every record logged during that request (errors, service moves)
carries `request_id` automatically (spec US2 scenario 1a). The background snapshot check runs in
a task created at startup, so it has no `request_id` (spec edge case).

**Why only printable ASCII up to 128 characters**: the value is untrusted. JSON escaping already
stops fake log lines, and the character and length limits stop oversized or binary values.

## 5. Event catalog and where each event is logged

| Event (`message`) | Level | Where | Fields |
|---|---|---|---|
| `request completed` | info | `main.py` middleware | method, path, status_code, duration_ms (+ request_id, client_request_id) |
| `pricing data unavailable` | error | `main.py` exception handler | path, error |
| `active pricing snapshot selected` | info | `active_snapshot.run_check`, at startup | snapshot_date, pinned |
| `active pricing snapshot changed` | info | `active_snapshot.run_check`, when switched | snapshot_date, previous_snapshot_date, pinned |
| `pricing snapshot waiting` | info | `active_snapshot.run_check` | snapshot_date, reason; logged only when a date first starts waiting or its reason changes, so it doesn't repeat every 5 minutes |
| `pricing snapshot missing regions` | warning | `active_snapshot.run_check`, on switch | snapshot_date, previous_snapshot_date, regions |
| `pricing snapshot check failed` | error | `active_snapshot.check_snapshots`, and the monitor loop in `main.py` | error (+ exception) |
| `icon coverage analyzed` | info | `icon_coverage.analyze` | snapshot_date, missing_icon_count, new_service_codes |
| `service has no icon` | debug | `icon_coverage.analyze` | snapshot_date, service_code, service_name, is_new |
| `icon coverage analysis failed` | error | `active_snapshot.run_check` | (+ exception) |
| `service moved` | info | `api/sku_selections._move_to_collection` | sku_selection_id, sku, service_code, source_collection_id, target_collection_id |
| `service move refused` | warning | same | the same fields plus reason (`not_movable`, `region_mismatch`) |

**Waiting-snapshot logging rule**: `run_check` compares the new waiting list with the previous
one, which is kept on the state, and logs only new or changed entries.

**Pure core stays unlogged**: `check_snapshots` keeps returning a `CheckResult` and stays free of
logging, except for the unreadable-folder error, which it already logs today. `run_check` logs
the transitions using `CheckResult` and the state from before and after the check.

## 6. Generator script `--log-file`

**Decision**: `scripts/generate_aws_service_icon_map.py` gains an optional `--log-file <path>`
argument.

- **Without it**: output is exactly as today, the printed report only (FR-009).
- **With it**: the script calls `configure_logging(level="INFO", fmt="json", stream=open(path, "w"))`
  and logs:
  - one `service icon matched` record per service, with service_code, service_name, icon_file
    (null for fallback) and match_type (`matched`, `fuzzy`, `override`, `data_transfer` or
    `fallback`);
  - one `family icon override` record per (service_code, product_family) override, with icon_file
    and match_type `family_override`;
  - one `icon copied` record per SVG copied, with icon_file.

The printed report still goes to standard output unchanged.

**Needed change**: `build_mapping` currently returns report lines. It will also return structured
rows, so the printed report and the log records come from the same data.

## 7. Secrets (FR-010)

**Findings**:
- No existing log call includes headers, bodies or passwords.
- The new request log records the path only.
- Auth routes (`/auth/login`, `/admin/users/{id}/password`) log only the standard request line.

**Decision**:
- Make no header or body fields at all, except the validated `client_request_id`.
- Add a test that runs the login and password-set flows and asserts that no captured record
  contains the password, a `pbkdf2_sha256$` hash, `Bearer ` or `authorization`.

## 8. Testing approach (Principle V)

Logging is operational tooling. Principle V's non-negotiable test-first scope covers pricing,
DuckDB and Postgres logic, but the behavior here is contract-like (the record shape and field
names), so the tests are still written first:

- **`tests/unit/test_logging_config.py`**: covers `configure_logging` rendering into a
  `StringIO`:
  - each line is JSON with timestamp (ISO 8601, `+00:00`), level and message;
  - `LOG_LEVEL` filtering;
  - a traceback stays in a single line, under `exception`;
  - a stdlib `logging.getLogger("uvicorn.error")` record has the same shape;
  - a non-JSON value (a `date`, a `UUID`) renders as text;
  - the `console` format renders without JSON;
  - an invalid `LOG_FORMAT` fails `Settings` validation;
  - calling it twice leaves exactly one root handler.
- **`tests/contract/test_request_logging.py`**, using `structlog.testing.capture_logs` or
  `caplog`:
  - the `request completed` fields;
  - the `X-Request-ID` header matches the record's `request_id`;
  - a valid client header → `client_request_id`;
  - an oversized or control-character header → ignored;
  - an error logged inside a request carries the same `request_id`.
- **`tests/unit/test_active_snapshot.py`** (extended):
  - the selected, changed, waiting (logged once, not on the next unchanged check), missing-regions
    and check-failed events, with their fields.
- **`tests/unit/test_icon_coverage.py`** (extended):
  - the info summary (count and new codes) and one debug record per service.
- **`tests/contract/test_sku_selections.py`** (extended):
  - the `service moved` and `service move refused` fields.
- **`tests/contract/test_log_secrets.py`**:
  - FR-010, as in §7.
- **Generator script**:
  - a unit test of the per-service row data from `build_mapping`, over a tiny fake icon folder and
    service list;
  - `--log-file` writes one JSON line per row.
