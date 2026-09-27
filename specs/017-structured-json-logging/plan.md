# Implementation Plan: Structured JSON Logging

**Branch**: `017-structured-json-logging` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/017-structured-json-logging/spec.md`

## Summary

Replace the backend's plain `logging.basicConfig` text output with **structlog**. Every record,
including those from Uvicorn and libraries, becomes one JSON line on standard output with
`timestamp` (ISO 8601 UTC), `level` and `message`. Records that need more context add
`snake_case` detail fields.

How it works:
- **One module** (`src/logging_config.py`) sets up a shared structlog processor chain. It uses
  `ProcessorFormatter` on the root stdlib handler, so stdlib and Uvicorn records render the same
  way.
- **A new `LOG_FORMAT` setting** (`json` | `console`) chooses the renderer.
- **The request middleware**:
  - binds a server-generated `request_id` (and a validated `client_request_id`) into contextvars;
  - logs `request completed` with its duration;
  - returns `X-Request-ID`.

  This replaces Uvicorn's access log.
- **Named events with detail fields** are added in these places:
  - the active-snapshot check: selected, changed, waiting (logged once per change), missing
    regions, and failed;
  - the icon-coverage analysis: an info summary and debug lines per service;
  - moving a service between boxes: moved and refused.
- **The icon-map generator** gains `--log-file`, which writes one JSON record per service, family
  override and copied icon.

See [research.md](./research.md).

## Technical Context

**Language/Version**: Python 3.12 (backend only; no frontend changes)

**Primary Dependencies**: FastAPI, Uvicorn, pydantic-settings, and a new `structlog>=26.1`
(MIT/Apache-2.0, pure Python)

**Storage**: N/A. No schema or Parquet changes; logs go to standard output (or to the
`--log-file` path for the generator).

**Testing**: pytest, with `structlog.testing.capture_logs` for event fields and `StringIO` stream
capture for the rendered JSON; ruff

**Target Platform**: Linux container / macOS dev; the log consumer is whatever collects standard
output

**Project Type**: Web service (backend of the web application)

**Performance Goals**: Negligible overhead. Rendering one JSON line per request adds microseconds
(a single `json.dumps` per record).

**Constraints**:
- Records are single-line.
- No secrets, headers or bodies are logged.
- An unserializable value never raises.
- Configuring logging twice must not duplicate output (tests, `--reload`).

**Scale/Scope**:
- About 12 named events.
- Four source files gain log calls: `main.py`, `active_snapshot.py`, `icon_coverage.py`,
  `sku_selections.py`.
- One script gains an option.
- One new module and one new setting.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment | Status |
|---|---|---|
| I. Pricing integrity | Logging only observes pricing and doesn't change it. No price computation is altered. | PASS |
| II. Parquet read-only, Postgres for user data | Nothing new is stored. Logs go to standard output or a file the operator chooses. | PASS |
| III. Provider-extensible | Log fields are generic (`service_code`, `sku`, `snapshot_date`). Nothing is specific to AWS beyond the existing AWS-only icon generator. | PASS |
| IV. Typed contract | No request or response schema changes. The only new HTTP surface is the `X-Request-ID` header, documented in contracts/log-format.md §3, so `schema.d.ts` doesn't need regenerating. | PASS |
| V. Test-first | Tests for the record shape, request IDs, each FR-008 event and the absence of secrets are written before the code (research §8). The event hooks in `active_snapshot` and `sku_selections` touch DuckDB and Postgres flows, so they follow the test-first rule. | PASS |
| VI. YAGNI, minimal dependencies | **New dependency: structlog.** Justified because you explicitly asked for it (see Complexity Tracking). It doesn't change the stack or add any service. No log shipping, rotation or tracing is added. | PASS (justified) |

**Post-design re-check (after Phase 1)**: still passing. The design adds one module, one setting
and one CLI option. There is no new storage, and the API schema doesn't change.

## Project Structure

### Documentation (this feature)

```text
specs/017-structured-json-logging/
├── plan.md              # This file
├── research.md          # Phase 0: pipeline, Uvicorn integration, request ID, event locations, tests
├── data-model.md        # Log record, request context, settings, generator rows
├── quickstart.md        # Validation guide
├── contracts/
│   └── log-format.md    # Record shape, event catalog, X-Request-ID header, generator --log-file
└── tasks.md             # Phase 2 (/speckit-tasks, not created here)
```

### Source Code (repository root)

```text
backend/
├── pyproject.toml                         # + structlog>=26.1 (uv add structlog)
├── .env.example                           # + LOG_FORMAT
├── src/
│   ├── logging_config.py                  # NEW: configure_logging(level, fmt, stream), get_logger
│   ├── config.py                          # + log_format: Literal["json","console"] = "json"
│   ├── main.py                            # configure_logging at import; request-ID middleware;
│   │                                      #   CORS expose_headers; structured error + monitor logs
│   ├── api/sku_selections.py              # service moved / service move refused events
│   └── pricing_data/
│       ├── active_snapshot.py             # selected/changed/waiting/missing-regions/failed events;
│       │                                  #   logged_waiting on state
│       └── icon_coverage.py               # icon coverage analyzed (info) + service has no icon (debug)
├── scripts/
│   └── generate_aws_service_icon_map.py   # --log-file; build_mapping returns structured rows
└── tests/
    ├── unit/
    │   ├── test_logging_config.py         # NEW: shape, level, exception, uvicorn, non-JSON, console,
    │   │                                  #   idempotent, invalid LOG_FORMAT
    │   ├── test_active_snapshot.py        # + snapshot events
    │   ├── test_icon_coverage.py          # + summary/debug events
    │   └── test_icon_map_generator_log.py # NEW: rows + --log-file output
    └── contract/
        ├── test_request_logging.py        # NEW: request completed, X-Request-ID, client_request_id
        ├── test_log_secrets.py            # NEW: FR-010 across login / password-set flows
        └── test_sku_selections.py         # + move events

docs/configuration.md                      # + LOG_FORMAT
```

**Structure Decision**: this is the existing web-application layout. All changes are in
`backend/`, plus one line in `docs/configuration.md`. The frontend is untouched; its browser
console output is out of scope, per the spec.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New runtime dependency (structlog), under Principle VI | You explicitly chose the library. It provides contextvar binding for `request_id`, the processor chain and a stdlib bridge, so Uvicorn and library logs share the JSON shape. | A hand-written stdlib `JSONFormatter` would need its own contextvar binding and exception handling, and wouldn't meet the explicit requirement to use structlog. |
