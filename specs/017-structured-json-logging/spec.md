# Feature Specification: Structured JSON Logging

**Feature Branch**: `017-structured-json-logging`

**Created**: 2026-09-26

**Status**: Draft

**Input**: User description: "Use structlog library for logging with json structured format containing at least the following 3 fields: timestamp (ISO 8601 format), log level, message. Log messages that could benefit from more detail can add additional fields (e.g. sku ids, icon file names etc)"

## Clarifications

### Session 2026-09-26

- Q: Should logs always be JSON, or also have a readable local-development format? → A: JSON by default; a `LOG_FORMAT` setting (`json` | `console`) switches to readable, colored lines with the same fields for local development.
- Q: Should every log line written while handling one request share a request ID? → A: Yes. The server generates a `request_id` per request, includes it on every record logged during that request, and returns it in an `X-Request-ID` response header. If the caller sends its own `X-Request-ID`, it is recorded separately as `client_request_id` (only if it is at most 128 printable characters; otherwise it is ignored), and never replaces the server's `request_id`.
- Q: Should the icon-map generator script keep its printed report as well as structured records? → A: Keep the readable report on standard output as today; write one structured JSON record per service (and per copied icon) only when a `--log-file <path>` option is given, to that file.
- Q: Should the backend's icon analysis log one summary line or one line per service without an icon? → A: One `info` summary line with `snapshot_date`, `missing_icon_count` and the `new_service_codes` list (services first seen in that snapshot), plus one `debug` line per service with no icon (`service_code`, `service_name`, `is_new`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every backend log line is one machine-readable JSON record (Priority: P1)

An operator or developer running the backend wants its logs to be easy to search, filter and send to a log tool. Today each line is free-form text in whatever layout the code and server happen to use. After this change, every line the backend writes is a single JSON object that always contains a timestamp, a level and a message. That includes the application's own messages, the web server's request and startup messages, and errors with tracebacks.

**Why this priority**: This is the core of the request. Without a consistent record shape, no log tooling can reliably parse the output.

**Independent Test**: Start the backend, make a few requests (including one that fails), and capture the output. Every line parses as JSON and has `timestamp`, `level` and `message`.

**Acceptance Scenarios**:

1. **Given** the backend is running, **When** it writes any log line, **Then** the line is a single valid JSON object on one line.
2. **Given** any log record, **When** it is parsed, **Then** it contains `timestamp` in ISO 8601 format with timezone (UTC), `level` (e.g. `info`, `warning`, `error`), and `message` (the human-readable text).
3. **Given** the web server's startup and request messages, **When** they are logged, **Then** they follow the same JSON shape as the application's own messages.
4. **Given** an unexpected error with a traceback, **When** it is logged, **Then** the record is still one JSON line, and the traceback is contained in a field of that record rather than printed as separate raw lines.
5. **Given** the configured log level (`LOG_LEVEL`, from 016), **When** messages below that level are emitted, **Then** they are not written.
6. **Given** `LOG_FORMAT=console`, **When** the backend logs, **Then** each record is a readable, colored line with the same timestamp, level, message and detail fields. With the setting unset or `json`, output is JSON.

---

### User Story 2 - Log records carry the details needed to investigate (Priority: P2)

When something goes wrong (a pricing snapshot doesn't activate, a service has no icon, a request fails), the person investigating wants the identifying details as separate fields they can filter on, rather than having to parse them out of message text. Examples are the snapshot date, SKU, service code, icon file name, request path, status code and duration.

**Why this priority**: This makes the structured format useful for troubleshooting, but the format itself (Story 1) is the foundation.

**Independent Test**: Trigger each of the events below and confirm that each one's record includes the listed fields with correct values.

**Acceptance Scenarios**:

1. **Given** an HTTP request completes, **When** it is logged, **Then** the record includes `method`, `path`, `status_code`, `duration_ms` and `request_id`, and the response carries the same value in `X-Request-ID`.
1a. **Given** an error or event is logged while a request is being handled, **When** its record is written, **Then** it carries that request's `request_id`.
1b. **Given** a caller sends `X-Request-ID: abc-123`, **When** the request is logged, **Then** records carry `client_request_id: "abc-123"` alongside the server's own `request_id`, and the response header still returns the server's `request_id`.
2. **Given** the pricing data can't be read, **When** the error is logged, **Then** the record includes the request `path` and the error detail.
3. **Given** the active pricing snapshot changes, or a newer snapshot is found waiting, **When** it is logged, **Then** the record includes the relevant snapshot dates, and for a waiting snapshot the reason.
4. **Given** the icon-coverage analysis runs, **When** it finishes, **Then** one `info` record includes `snapshot_date`, `missing_icon_count` and `new_service_codes`. At `LOG_LEVEL=DEBUG`, each service with no icon also has its own record with `service_code`, `service_name` and `is_new`.
5. **Given** a service is moved to another box, or a move is refused, **When** it is logged, **Then** the record includes the SKU selection id, the SKU, the source and target box ids, and for a refusal the reason.
6. **Given** the icon-map generator script runs with `--log-file report.jsonl`, **When** it finishes, **Then** `report.jsonl` holds one JSON record per service (with `service_code`, `icon_file`, `match_type`) and per copied icon, and the printed report on screen is unchanged. Without `--log-file`, no JSON is written.

---

### Edge Cases

- A message contains quotes, newlines or non-ASCII characters: the record is still valid, single-line JSON (the values are escaped).
- A detail value isn't naturally text (a date, a number, a UUID): it is written as a JSON-safe value (a string or number), never causing a logging failure.
- Logging itself fails (for example, an unserializable field): the application keeps running, and the record is written with the offending value converted to text.
- Code or libraries that log through the standard logging interface (the web server, database driver, background task) still produce records in the same JSON shape.
- Running the automated tests: logging doesn't make tests fail, and tests can capture and inspect log records.
- Secrets: request headers, passwords and bearer tokens are never included as fields.
- A caller sends an oversized or non-printable `X-Request-ID`: it is ignored (no `client_request_id`), and the request proceeds normally.
- Logs written outside any request (startup, background snapshot checks) have no `request_id`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The backend MUST write every log record as a single-line JSON object to standard output by default.
- **FR-001a**: A `LOG_FORMAT` setting (environment-overridable, like the other settings from 016) MUST accept `json` (the default) or `console`. With `console`, records are written as readable, colored lines carrying the same fields; any other value MUST prevent startup with a message naming the setting.
- **FR-002**: Every record MUST include `timestamp` (ISO 8601 with timezone, UTC), `level` (lower-case level name) and `message` (the human-readable text).
- **FR-003**: Records from the web server (startup, shutdown, per-request) and from any library logging through the standard logging interface MUST use the same JSON shape as the application's own records.
- **FR-004**: Records for errors with a traceback MUST keep the traceback inside the single JSON record (e.g. an `exception` field).
- **FR-005**: The minimum level written MUST follow the existing `LOG_LEVEL` setting.
- **FR-006**: The request log MUST include `method`, `path`, `status_code` and `duration_ms`, and MUST NOT include request headers (other than the validated `client_request_id` below), query-string secrets or bodies.
- **FR-006a**: Each request MUST get a server-generated `request_id` (unique per request) that is included on every record logged while handling that request, including errors and the events in FR-008, and is returned to the caller in an `X-Request-ID` response header.
- **FR-006b**: If the request carries an `X-Request-ID` header, its value MUST be recorded as `client_request_id` on that request's records, but only if it is at most 128 printable characters; otherwise it MUST be ignored. It MUST never replace `request_id` or be echoed in the response header.
- **FR-007**: Existing log messages MUST be converted so that the identifying values they currently embed in text (request path, error detail, snapshot details) are separate fields, with a plain `message`.
- **FR-008**: The backend MUST log these events with the listed detail fields:
  - (a) the active pricing snapshot is chosen at startup or changes (`snapshot_date`, `previous_snapshot_date`, `pinned`);
  - (b) a newer snapshot is waiting (`snapshot_date`, `reason`);
  - (c) a pricing snapshot check fails (`error`);
  - (d) the icon-coverage analysis completes: one `info` record (`snapshot_date`, `missing_icon_count`, `new_service_codes`), plus one `debug` record per service with no icon (`service_code`, `service_name`, `is_new`);
  - (e) a service is moved to another box, or a move is refused (`sku_selection_id`, `sku`, `service_code`, `source_collection_id`, `target_collection_id`, and `reason` when refused).
- **FR-009**: The icon-map generator script MUST keep its current readable report on standard output. When run with `--log-file <path>`, it MUST also write one JSON record per service (`service_code`, `service_name`, `icon_file`, `match_type` of matched, fuzzy, override, family override, data transfer or fallback) and one per copied icon (`icon_file`), with the same `timestamp`, `level` and `message` fields, to that file. Without the option, it writes no JSON output.
- **FR-010**: Passwords, password hashes, bearer tokens and authorization headers MUST NOT appear in any log record.
- **FR-011**: A value that can't be represented as JSON MUST NOT cause a logging failure; it MUST be written as text.
- **FR-012**: Automated tests MUST be able to capture log records and assert on their fields.

### Key Entities

- **Log Record**: One JSON object per line. It has the always-present `timestamp`, `level` and `message` fields, plus optional detail fields named for what they hold (e.g. `request_id`, `client_request_id`, `snapshot_date`, `sku`, `service_code`, `icon_file`, `path`, `status_code`, `duration_ms`, `exception`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the default format, 100% of lines written by the running backend (startup, requests, errors, background checks) parse as JSON and contain `timestamp`, `level` and `message`.
- **SC-002**: 100% of `timestamp` values parse as ISO 8601 date-times with a UTC offset.
- **SC-003**: For each event in FR-008, the listed detail fields are present and correct in 100% of occurrences in the automated tests.
- **SC-004**: 0 log records contain a password, password hash, bearer token or authorization header value while exercising the login, user-creation, password-change and authenticated-request flows in the automated tests.
- **SC-005**: Someone investigating can find all log records about one SKU, snapshot date, request path or request (`request_id`) by filtering on a single field, with no text parsing.

## Assumptions

- Scope is the backend (the API server, its background snapshot check, and the backend scripts). The browser frontend's console output is out of scope.
- Output goes to standard output as one JSON object per line. Log shipping, files and rotation are left to whatever runs the process.
- JSON is the default format everywhere. The `console` format is intended only for local development, and no production setup should need it.
- Level names are lower-case (`debug`, `info`, `warning`, `error`, `critical`), and timestamps are UTC.
- The user explicitly named the logging library (structlog). The plan will adopt it as a new dependency, justified by this explicit requirement (Constitution Principle VI). It doesn't change the application's stack or data stores.
- Field names use `snake_case`. The `message` field holds what was previously the free-form log text.
- Database migration output (Alembic's own logging configuration) keeps working. It is converted to JSON only where it runs inside the backend process.
