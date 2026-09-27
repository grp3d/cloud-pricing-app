# Quickstart: Validating Structured JSON Logging

## Prerequisites

- The backend dev environment from earlier features is set up: `cd backend && uv sync`, with
  Postgres running and migrated.
- `jq` is installed, for inspecting the output.

## 1. Automated tests

```bash
cd backend
uv run pytest tests/unit/test_logging_config.py tests/contract/test_request_logging.py \
  tests/contract/test_log_secrets.py -q
uv run pytest -q    # full suite: nothing regresses, and no test is broken by log output
uv run ruff check src tests scripts
```

**Expected**: all tests pass. They cover the record shape, the level threshold, tracebacks,
Uvicorn records, non-JSON values, the console format, request IDs, the snapshot, icon and move
events, and the absence of secrets.

## 2. Every line is JSON (SC-001, SC-002)

```bash
cd backend
uv run uvicorn src.main:app --port 8000 > /tmp/app.log 2>&1 &
curl -s localhost:8000/health > /dev/null
curl -s localhost:8000/does-not-exist > /dev/null
kill %1
jq -c '{timestamp, level, message}' /tmp/app.log                    # every line parses
jq -e 'select(.timestamp == null or .level == null or .message == null)' /tmp/app.log \
  && echo "MISSING FIELDS" || echo "ok"
```

**Expected**:
- Uvicorn's startup and shutdown lines are JSON.
- There is one `request completed` record per request, with `method`, `path`, `status_code`,
  `duration_ms` and `request_id`.
- There is no second (Uvicorn access) line per request.

## 3. Request ID (FR-006a/b)

```bash
curl -si -H 'X-Request-ID: abc-123' localhost:8000/health | grep -i x-request-id
```

**Expected**:
- The response header is a 32-character hex ID, not `abc-123`.
- The matching log record has `request_id` equal to that ID and `client_request_id: "abc-123"`.
- Sending a 200-character header produces no `client_request_id`.

## 4. Console format (FR-001a)

```bash
LOG_FORMAT=console uv run uvicorn src.main:app --port 8000     # colored readable lines
LOG_FORMAT=xml uv run uvicorn src.main:app --port 8000         # fails at startup, naming log_format
```

## 5. Snapshot and icon events (FR-008 a–d)

Start the backend with `LOG_LEVEL=DEBUG`. Then check:

```bash
jq 'select(.message | test("snapshot|icon"))' /tmp/app.log
```

**Expected**:
- `active pricing snapshot selected` appears at startup, with `snapshot_date`.
- `icon coverage analyzed` appears, with `missing_icon_count` and `new_service_codes`.
- One `service has no icon` record appears per service without an icon.
- A snapshot that's waiting logs `pricing snapshot waiting` once, not every 5 minutes.

## 6. Service moves (FR-008 e)

In the UI, drag a service icon into another box in the same region, then into a box in a
different region. The log shows:
- `service moved`, with `sku`, `service_code`, and the source and target box IDs;
- `service move refused`, with `reason: "region_mismatch"`.

Both records carry the request's `request_id`.

## 7. Generator `--log-file` (FR-009)

```bash
cd backend
uv run python scripts/generate_aws_service_icon_map.py --log-file /tmp/icons.jsonl
jq -r .match_type /tmp/icons.jsonl | sort | uniq -c
```

**Expected**:
- The printed report is unchanged.
- `/tmp/icons.jsonl` holds one record per service (and per family override and copied icon).
- Running without `--log-file` writes no JSON.
