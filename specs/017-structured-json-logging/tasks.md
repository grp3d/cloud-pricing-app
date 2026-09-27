---

description: "Task list for 017-structured-json-logging"
---

# Tasks: Structured JSON Logging

**Input**: Design documents from `/specs/017-structured-json-logging/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/log-format.md, quickstart.md

**Tests**: Included. The plan (Constitution Check V, research.md §8) requires tests to be written
first. Each test task MUST be written and seen to FAIL before its implementation task.

**Organization**: Tasks are grouped by user story, so each story can be implemented and tested
independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on unfinished tasks)
- **[Story]**: The user story the task belongs to (US1, US2)
- All paths are relative to the repository root. Backend commands run from `backend/`.

## Shared conventions (apply to every task)

- Loggers are created with `get_logger(name)` from `src/logging_config.py`, where `name` is under
  `cloud_pricing` (`cloud_pricing`, `cloud_pricing.active_snapshot`, `cloud_pricing.icon_coverage`,
  `cloud_pricing.sku_selections`). No module calls `logging.basicConfig` or `logging.getLogger`
  for its own records any more.
- Log calls pass a fixed `message` string (exactly as listed in contracts/log-format.md §2) plus
  keyword detail fields in `snake_case`, e.g. `logger.info("service moved", sku=..., ...)`. Never
  use `%s` formatting or f-strings to embed values in the message.
- UUIDs and dates passed as fields are converted with `str(...)`, so tests can compare them to
  strings.
- Tests read the rendered records through the `log_output` fixture (T008), which returns the
  parsed JSON lines as a list of dicts. Don't use `structlog.testing.capture_logs`, because it
  skips `merge_contextvars` and so would not show `request_id`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the dependency and document the new setting.

- [X] T001 Add structlog: run `cd backend && uv add "structlog>=26.1"`, which updates `backend/pyproject.toml` and `backend/uv.lock`. Confirm `uv run python -c "import structlog; print(structlog.__version__)"` prints 26.1 or later.
- [X] T002 [P] In `backend/.env.example`, directly below the `# LOG_LEVEL=INFO` line, add `# LOG_FORMAT=json` with a comment line above it: `# Log output format: json (default, one JSON object per line) or console (colored, readable; local development only)`.
- [X] T003 [P] In `docs/configuration.md`, add a row directly below the `LOG_LEVEL` row: `` | `LOG_FORMAT` | `json` \| `console` | `json` | Log output format. `json` writes one JSON object per line with `timestamp`, `level` and `message`; `console` writes colored, readable lines for local development. Any other value stops startup. | ``. Also change the `LOG_LEVEL` description to `Minimum level of log records written.`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The `LOG_FORMAT` setting, the logging pipeline module and the test fixture. Both
user stories depend on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 [P] Write failing tests in `backend/tests/unit/test_settings.py`, following the file's existing style for `LOG_LEVEL`:
  - `Settings().log_format == "json"` when `LOG_FORMAT` is unset;
  - `LOG_FORMAT=console` (via `monkeypatch.setenv`) gives `"console"`;
  - `LOG_FORMAT=xml` raises `pydantic.ValidationError`, and `"log_format"` appears in the error text.
- [X] T005 Add `log_format: Literal["json", "console"] = "json"` to `Settings` in `backend/src/config.py`, directly below `log_level`, with a one-line comment referencing 017 FR-001a. Make T004 pass.
- [X] T006 [P] Write failing core-shape tests in a new `backend/tests/unit/test_logging_config.py`. Each test calls `configure_logging(level=..., fmt="json", stream=io.StringIO())` and parses `stream.getvalue().splitlines()` with `json.loads`. Cover:
  - `get_logger("cloud_pricing.test").info("hello", sku="ABC")` writes exactly one line. It has `message == "hello"`, `level == "info"`, `sku == "ABC"`, `logger == "cloud_pricing.test"`, and no `event` key. `timestamp` parses with `datetime.fromisoformat` and has `utcoffset() == timedelta(0)` and a `+00:00` suffix.
  - At `level="INFO"`, a `debug` call writes nothing. At `level="WARNING"`, an `info` call writes nothing.
  - A message containing `"`, `\n` and `é` is still one line and round-trips exactly through `json.loads`.
  - Fields holding a `datetime.date`, a `uuid.UUID`, a `decimal.Decimal` and an instance of a custom class with no JSON form render as strings, and the call doesn't raise (FR-011).
  - Calling `configure_logging` twice leaves exactly one handler on `logging.getLogger()` (the root logger), and one log call writes exactly one line.
- [X] T007 Create `backend/src/logging_config.py` so that T006 passes (research.md §1). It has a module docstring referencing 017 and contracts/log-format.md, and exposes:
  - `configure_logging(level: str, fmt: Literal["json", "console"], stream: TextIO = sys.stdout) -> None`. It builds `shared = [structlog.contextvars.merge_contextvars, structlog.stdlib.add_logger_name, structlog.stdlib.add_log_level, structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"), structlog.processors.StackInfoRenderer(), structlog.processors.format_exc_info, structlog.processors.EventRenamer("message")]`.
    - The renderer is `structlog.processors.JSONRenderer(default=str)` for `json`, or `structlog.dev.ConsoleRenderer(colors=True, event_key="message")` for `console`.
    - It creates one `logging.StreamHandler(stream)` whose formatter is `structlog.stdlib.ProcessorFormatter(foreign_pre_chain=shared, processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer])`.
    - It replaces all existing root handlers with that handler and sets the root level to `level`.
    - It calls `structlog.configure(processors=[structlog.stdlib.filter_by_level, *shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter], logger_factory=structlog.stdlib.LoggerFactory(), wrapper_class=structlog.stdlib.BoundLogger, cache_logger_on_first_use=False)`. The full `shared` chain appears in both places on purpose. `foreign_pre_chain` runs only for records from ordinary `logging` loggers, and the `structlog.configure` chain runs only for structlog's own loggers, so every record passes through `shared` exactly once.
  - `get_logger(name: str) -> structlog.stdlib.BoundLogger`, a thin wrapper around `structlog.get_logger(name)`.
- [X] T008 Add a `log_output` pytest fixture to `backend/tests/conftest.py`:
  - It calls `configure_logging(level="DEBUG", fmt="json", stream=buf)` with a fresh `io.StringIO`, and calls `structlog.contextvars.clear_contextvars()`.
  - It yields a zero-argument callable that returns `[json.loads(line) for line in buf.getvalue().splitlines()]`.
  - On teardown it calls `clear_contextvars()` and `configure_logging(settings.log_level, settings.log_format)`.
  - Add a one-line docstring saying it captures the rendered JSON records (017 FR-012).

**Checkpoint**: `uv run pytest tests/unit/test_settings.py tests/unit/test_logging_config.py -q` passes. The pipeline exists but the app doesn't use it yet.

---

## Phase 3: User Story 1 - Every backend log line is one machine-readable JSON record (Priority: P1) 🎯 MVP

**Goal**: Everything the running backend writes (its own messages, Uvicorn's startup and shutdown
messages, library records, tracebacks, one line per request) is a single JSON object with
`timestamp`, `level` and `message`. `LOG_FORMAT=console` switches to readable lines.

**Independent Test**: Follow quickstart.md §2 and §4. Start the backend, make a good request and a
404, and stop it. Every line in the output parses with `jq` and has all three fields. There is no
Uvicorn access line. `LOG_FORMAT=console` shows colored lines, and `LOG_FORMAT=xml` stops startup.

### Tests for User Story 1 ⚠️ (write first, see them fail)

- [X] T009 [P] [US1] Add tests to `backend/tests/unit/test_logging_config.py`:
  - **Traceback**: inside `except ZeroDivisionError`, `logger.exception("boom")` writes exactly one line. Its `exception` field contains `Traceback` and `ZeroDivisionError`, and its `level` is `error`.
  - **Stdlib record**: `logging.getLogger("uvicorn.error").info("Started server process [%d]", 123)` renders one JSON line with `message == "Started server process [123]"`, `level == "info"`, `logger == "uvicorn.error"` and a UTC `timestamp`. A record logged with `extra={"color_message": "\x1b[1mx\x1b[0m"}`, as Uvicorn's startup lines are, has no `color_message` key.
  - **Uvicorn loggers**: first give `uvicorn` and `uvicorn.access` a dummy handler and `propagate=False`, as Uvicorn's config does. After `configure_logging`, each of `uvicorn`, `uvicorn.error` and `uvicorn.access` has no handlers and `propagate is True`, and `logging.getLogger("uvicorn.access").level == logging.WARNING`.
  - **Console format**: with `fmt="console"`, `get_logger("x").info("hello", sku="ABC")` writes a line that contains `hello` and `ABC`, and on which `json.loads` raises.
- [X] T010 [P] [US1] Create `backend/tests/contract/test_request_logging.py` using the `client` and `log_output` fixtures (and `@pytest.mark.asyncio`, as in the other contract tests). Assert:
  - `GET /health` produces exactly one record with `message == "request completed"`. It has `method == "GET"`, `path == "/health"`, `status_code == 200` (an int), `duration_ms` a float ≥ 0 and `logger == "cloud_pricing"`.
  - `GET /does-not-exist` produces a `request completed` record with `status_code == 404`.
  - `GET /health?token=s3cr3t` produces a record with `path == "/health"`, and `s3cr3t` appears in no record (FR-006).

### Implementation for User Story 1

- [X] T011 [US1] In `configure_logging` in `backend/src/logging_config.py`, for each of the logger names `uvicorn`, `uvicorn.error` and `uvicorn.access`: clear `handlers`, set `propagate = True`, and set `uvicorn.access` to `logging.WARNING`, because the app's `request completed` record replaces Uvicorn's access line (research.md §2). T009 should now pass.
- [X] T012 [US1] In `backend/src/main.py`:
  - replace `logging.basicConfig(level=settings.log_level)` with `configure_logging(settings.log_level, settings.log_format)`;
  - replace `logger = logging.getLogger("cloud_pricing")` with `logger = get_logger("cloud_pricing")`;
  - remove `import logging` if nothing else uses it.
  `configure_logging` must still run at import time, so that it runs after Uvicorn has applied its own config.
- [X] T013 [US1] In `backend/src/main.py`, rewrite the `log_requests` middleware:
  - record `start = time.perf_counter()` before `call_next`;
  - after it, call `logger.info("request completed", method=request.method, path=request.url.path, status_code=response.status_code, duration_ms=round((time.perf_counter() - start) * 1000, 1))`;
  - return the response.
  Log only `request.url.path`, never the full URL or the query string. T010 should now pass.
- [X] T014 [US1] Convert the remaining existing log calls to the structured style (FR-007):
  - In `backend/src/pricing_data/active_snapshot.py`, replace `import logging` and `logging.getLogger("cloud_pricing.active_snapshot")` with `get_logger("cloud_pricing.active_snapshot")`.
  - In `check_snapshots`, change `logger.error("pricing snapshot check failed: %s", exc)` to `logger.error("pricing snapshot check failed", error=str(exc))`.
  - In `run_check`, keep `logger.exception("icon coverage analysis failed")` as is.
  - In `_snapshot_monitor` in `backend/src/main.py`, change it to `except Exception as exc:  # noqa: BLE001` followed by `logger.exception("pricing snapshot check failed", error=str(exc))`, so that both places that log this event include `error` (contracts/log-format.md §2).
  - Confirm that both render with an `exception` field.
- [X] T015 [US1] Run `cd backend && uv run pytest -q` and fix any test that broke because of the new output (for example, tests that inspected the old text), without weakening what they assert. Then run quickstart.md §2 and §4 by hand and confirm the expected results.

**Checkpoint**: US1 works on its own. Every line is JSON (or console text), and there is one `request completed` line per request.

---

## Phase 4: User Story 2 - Log records carry the details needed to investigate (Priority: P2)

**Goal**: Request IDs on every record of a request, plus the named events from FR-008 and the
generator's `--log-file`, each carrying filterable detail fields. No secrets are ever logged.

**Independent Test**: Follow quickstart.md §3, §5, §6 and §7. The `X-Request-ID` header matches
the record's `request_id`, the snapshot, icon and move events carry their fields, and
`--log-file` writes one JSON line per service.

### Tests for User Story 2 ⚠️ (write first, see them fail)

- [X] T016 [P] [US2] Add request-ID tests to `backend/tests/contract/test_request_logging.py` (FR-006a/b, contracts/log-format.md §3):
  - **Server ID**: `GET /health` returns an `X-Request-ID` header matching `^[0-9a-f]{32}$`, equal to the `request_id` on its `request completed` record. Two requests get different IDs.
  - **Client ID**: with request header `X-Request-ID: abc-123`, the record has `client_request_id == "abc-123"`, and the response header is not `abc-123` and still matches the hex pattern.
  - **Rejected client IDs**: a 129-character `X-Request-ID`, and one containing a non-ASCII byte (send `"caf\xe9".encode("latin-1")` as the header value), give records with no `client_request_id` key and a 200 status.
  - **CORS**: a request with header `Origin` set to the first value of `settings.cors_allowed_origins` gets `x-request-id` in its `access-control-expose-headers` response header.
  - **Error inside a request**: point `config_module.settings.aws_pricing_parquet_dir` at a missing folder, as `test_data_source_outage_returns_503` in `backend/tests/contract/test_catalog.py` does, and call `GET /api/v1/catalog/skus?service_code=AmazonEC2&region=us-east-1` with `auth_headers`. It returns 503. The log has a `pricing data unavailable` record at `level == "error"` with `path == "/api/v1/catalog/skus"` and a non-empty `error`, and its `request_id` equals both the response `X-Request-ID` and the `request_id` on the `request completed` record (US2 scenarios 1a and 2).
  - **Outside a request**: a record logged outside any request (e.g. `get_logger("cloud_pricing").info("x")` called directly in the test) has no `request_id`.
- [X] T017 [P] [US2] Add snapshot event tests to `backend/tests/unit/test_active_snapshot.py`, using the existing `fresh_state` fixture, `make_snapshot_tree` and `active_snapshot.run_check`, plus `log_output`. Set `monkeypatch.setattr(active_snapshot, "_analysis_hook", lambda *a: None)` unless the test is about the analysis (FR-008 a–c):
  - **Selected**: `run_check(at_startup=True)` with `{D1: {}, D2: {}}` logs `active pricing snapshot selected` with `snapshot_date == D2` and `pinned is False`. With `settings.active_snapshot_date` pinned to `date.fromisoformat(D1)`, it logs `snapshot_date == D1` and `pinned is True`.
  - **Changed**: after a startup check on D1, adding a complete D2 tree and calling `run_check()` logs `active pricing snapshot changed` with `snapshot_date == D2`, `previous_snapshot_date == D1` and `pinned is False`. An unchanged check logs no `changed` record.
  - **Waiting**: a newer date without markers logs exactly one `pricing snapshot waiting` record with that `snapshot_date` and the same `reason` as `STATE.waiting`. A second `run_check()` with nothing changed logs no further `waiting` record. Changing the reason (for example, by adding the marker to one more table) logs it again with the new reason.
  - **Missing regions**: a switch to a date that lost a region logs `pricing snapshot missing regions` at `warning`, with `snapshot_date`, `previous_snapshot_date` and `regions` equal to the lost-region list on the `missing_regions` issue. Mirror the existing missing-regions test in the file for the tree setup.
  - **Check failed**: `aws_pricing_parquet_dir` pointing at a missing folder logs `pricing snapshot check failed` at `error`, with a non-empty `error`.
  - **Analysis failed**: an `_analysis_hook` that raises `RuntimeError("x")` logs `icon coverage analysis failed` at `error`, with an `exception` field containing `RuntimeError`.
- [X] T018 [P] [US2] Add tests to `backend/tests/unit/test_icon_coverage.py`, reusing the file's `_tree` helper and `log_output` (FR-008 d). Build an `ActiveSnapshotState` with `active_date` set and call `icon_coverage.analyze(state, tmp_path, None)`:
  - Exactly one `icon coverage analyzed` record at `info`, with `snapshot_date`, `missing_icon_count == len([i for i in state.issues if i.kind == "missing_icon"])`, and `new_service_codes` equal to the sorted service codes of those issues where `is_new` is true.
  - One `service has no icon` record at `debug` per missing-icon issue, with `snapshot_date`, `service_code`, `service_name` and `is_new` matching the issue.
  - A snapshot where every service has an icon logs `missing_icon_count == 0` and `new_service_codes == []`, with no debug records.
- [X] T019 [P] [US2] Add tests to `backend/tests/contract/test_sku_selections.py` using `log_output`. Reuse the file's existing move tests (the `PATCH /sku-selections/{id}` with `collection_id` flows for FR-004a/b) for setup (FR-008 e):
  - **Successful move**: logs one `service moved` record at `info`, with `sku_selection_id`, `sku`, `service_code`, `source_collection_id` and `target_collection_id` as strings equal to the ids used, and a `request_id` equal to the response `X-Request-ID`.
  - **Region mismatch**: logs `service move refused` at `warning`, with the same fields and `reason == "region_mismatch"`.
  - **Connector-attached selection**: logs `service move refused` with `reason == "not_movable"` and `source_collection_id` set to `None`.
- [X] T020 [P] [US2] Create `backend/tests/contract/test_log_secrets.py` (FR-010, SC-004) using `client`, `admin_headers` and `log_output`. Exercise the flows that carry secrets, following the existing flows in `backend/tests/contract/test_auth.py` and `test_admin_users.py`:
  - log in with a username and password;
  - create a user with a password as admin;
  - set a user's password as admin;
  - make one authenticated request with the returned bearer token.
  Then join every rendered record into one string and assert that none of these appear in it (case-insensitive where noted): the plain passwords used; `pbkdf2_sha256$`; `Bearer ` (case-insensitive); the token value; `authorization` (case-insensitive).
- [X] T021 [P] [US2] Create `backend/tests/unit/test_icon_map_generator_log.py` (FR-009). Load the script with `importlib.util.spec_from_file_location("generate_aws_service_icon_map", <backend>/scripts/generate_aws_service_icon_map.py)`. Use `tmp_path` fake SVG paths and a small `names` dict covering:
  - an exact match;
  - a fuzzy match;
  - a code in the script's `OVERRIDES` (take any key from the module);
  - `DATA_TRANSFER_SERVICE_CODE`;
  - an unmatched code.
  Also pass a `families` set that includes one pair from `FAMILY_OVERRIDES`, and give `icons` entries for every stem that `OVERRIDES` and `FAMILY_OVERRIDES` reference.

  Assert:
  - **Rows**: `build_mapping` returns rows with `match_type` values `matched`, `fuzzy`, `override`, `data_transfer` and `fallback` for the respective codes. The fallback row has `icon_file is None`, other rows have `icon_file == f"{stem}.svg"`, every row has `service_name` from `names`, and there is one `family_override` row per `FAMILY_OVERRIDES` entry, with `product_family`.
  - **Report**: the report lines (`build_mapping(...)[2]`) equal a literal `EXPECTED_REPORT: list[str]` stored in the test. Before starting T028, run the unchanged `build_mapping` on this test's inputs and paste its output in as `EXPECTED_REPORT`. Any change to the report text then fails the test.
  - **Log records**: calling the new `log_mapping(rows, copied_icons)` helper after `configure_logging(level="INFO", fmt="json", stream=buf)` writes, for each service row, one `service icon matched` line with `service_code`, `service_name`, `icon_file` and `match_type`; one `family icon override` line per family row; and one `icon copied` line per copied file, with `icon_file`. Every line has `timestamp`, `level` and `message`.
  - **No `--log-file`**: `main()` run with `--log-file` absent creates no file other than the normal outputs. Monkeypatch the `OUT_TS`, `OUT_JSON` and `OUT_ICONS` paths and the helpers `_service_icons`, `_special_icons`, `_latest_snapshot` and `_pricing_services` to keep it fast.

### Implementation for User Story 2

- [X] T022 [US2] Add request IDs to the `log_requests` middleware in `backend/src/main.py` (research.md §4):
  - At the start, call `structlog.contextvars.clear_contextvars()`, set `request_id = uuid.uuid4().hex`, and call `structlog.contextvars.bind_contextvars(request_id=request_id)`.
  - If `request.headers.get("x-request-id")` fully matches a module-level `_CLIENT_REQUEST_ID = re.compile(r"[\x20-\x7E]{1,128}")`, also bind `client_request_id`.
  - After `call_next`, set `response.headers["X-Request-ID"] = request_id` (never the client's value), and log `request completed` as before.
- [X] T023 [US2] In `backend/src/main.py`, add `expose_headers=["X-Request-ID"]` to the `CORSMiddleware` arguments.
- [X] T024 [US2] In `backend/src/main.py`, change `pricing_data_unavailable_handler` to `logger.error("pricing data unavailable", path=request.url.path, error=str(exc))` (FR-007, US2 scenario 2). Confirm that the middleware wraps the exception handlers, so the record carries the request's `request_id`: T016's error test must pass. If it doesn't, bind the contextvars in a pure ASGI middleware instead.
- [X] T025 [US2] In `backend/src/pricing_data/active_snapshot.py`, add the snapshot events (FR-008 a–c, research.md §5):
  - Add `logged_waiting: dict[str, str] = field(default_factory=dict)` to `ActiveSnapshotState`.
  - In `run_check`, record `was_initialized = STATE.initialized` before `check_snapshots`. After it, and only when `STATE.last_check_error is None`:
    - (a) If `at_startup` or not `was_initialized`, log `active pricing snapshot selected` with `snapshot_date=STATE.active_date` and `pinned=STATE.pinned`. Else, if `result.switched`, log `active pricing snapshot changed` with `snapshot_date`, `previous_snapshot_date=result.previous_date` and `pinned`.
    - (b) On a switch, if `STATE.issues` has a `missing_regions` issue for the new date, log `pricing snapshot missing regions` at `warning` with `snapshot_date`, `previous_snapshot_date` and `regions`.
    - (c) For each `w` in `STATE.waiting` where `STATE.logged_waiting.get(w.snapshot_date) != w.reason`, log `pricing snapshot waiting` with `snapshot_date` and `reason`. Then set `STATE.logged_waiting = {w.snapshot_date: w.reason for w in STATE.waiting}`.
  - Keep `check_snapshots` free of new logging (research.md §5, "pure core stays unlogged").
- [X] T026 [US2] In `backend/src/pricing_data/icon_coverage.py`, add `logger = get_logger("cloud_pricing.icon_coverage")`. In `analyze`, after computing `unmatched`:
  - for each issue, log `logger.debug("service has no icon", snapshot_date=state.active_date, service_code=i.service_code, service_name=i.service_name, is_new=bool(i.is_new))`;
  - then log `logger.info("icon coverage analyzed", snapshot_date=state.active_date, missing_icon_count=len(unmatched), new_service_codes=sorted(i.service_code for i in unmatched if i.is_new))`.
  T018 should now pass.
- [X] T027 [US2] In `backend/src/api/sku_selections.py`, add `logger = get_logger("cloud_pricing.sku_selections")`. In `_move_to_collection`, build `fields = dict(sku_selection_id=str(selection.id), sku=selection.sku, service_code=selection.service_code, source_collection_id=str(selection.collection_id) if selection.collection_id else None, target_collection_id=str(target_id))`, then:
  - before returning the `not_movable` response, log `logger.warning("service move refused", reason="not_movable", **fields)`;
  - before returning the `region_mismatch` response, log `logger.warning("service move refused", reason="region_mismatch", **fields)`;
  - after `selection.collection_id = target.id`, log `logger.info("service moved", **fields)`.
  Don't log for the 404 (different architecture) path. T019 should now pass.
- [X] T028 [US2] Update `backend/scripts/generate_aws_service_icon_map.py` (FR-009, research.md §6):
  - **Rows from `build_mapping`**: `build_mapping` also returns a list of row dicts, `{service_code, service_name, icon_file, match_type}`, built in the existing loop. Use `match_type="data_transfer"` with `icon_file=None` for `DATA_TRANSFER_SERVICE_CODE`, `"override"` for `OVERRIDES`, `"matched"` or `"fuzzy"` for auto matches, and `"fallback"` with `icon_file=None` for unmatched codes. Append one `{service_code, product_family, icon_file, match_type: "family_override"}` row per `FAMILY_OVERRIDES` entry. The report lines stay byte-for-byte unchanged.
  - **Return value**: update the return type to `tuple[dict[str, str], dict[str, dict[str, str]], list[str], list[dict[str, str | None]]]`, and update the `main()` call site.
  - **`log_mapping`**: add `log_mapping(rows, copied_icons: list[str]) -> None`. It logs, with `get_logger("cloud_pricing.icon_map")`, `service icon matched` per service row, `family icon override` per family row, and `icon copied` (with `icon_file`) per copied SVG file name.
  - **`--log-file`**: add `parser.add_argument("--log-file", type=Path, help="also write one JSON log record per service and copied icon to this file")`. In `main()`, collect the copied file names in the copy loops. When `args.log_file` is set, open it with `"w"` and `encoding="utf-8"` and call `configure_logging(level="INFO", fmt="json", stream=fh)`, then `log_mapping(rows, copied)`. The script imports `configure_logging` and `get_logger` from `src.logging_config`, the same way it already imports `settings`.
  - **Docs**: update the module docstring's usage line to mention `--log-file`. T021 should now pass.

**Checkpoint**: US1 and US2 both work. `uv run pytest -q` passes, and quickstart.md §3, §5, §6 and §7 show the expected fields.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final checks across both stories.

- [X] T029 [P] Fix the command in `specs/017-structured-json-logging/quickstart.md` §7 and `contracts/log-format.md` §4: the script requires `--icons <aws_architecture_icons dir>`. Change it to `uv run python scripts/generate_aws_service_icon_map.py --icons <dir> [--log-file PATH]`.
- [X] T030 [P] Search the backend for leftover plain logging: `grep -rn "logging.getLogger\|basicConfig\|logger\.\w*(\"[^\"]*%s" backend/src backend/scripts` should show nothing except the uvicorn logger handling in `backend/src/logging_config.py`. Convert any leftover calls to fixed-message plus fields.
- [X] T031 Run `cd backend && uv run ruff check src tests scripts && uv run ruff format --check src tests scripts && uv run pytest -q`. All checks pass, and the output shows no stray non-JSON log lines from the app.
- [X] T032 Run all of quickstart.md (§1–§7) by hand against a running backend with real pricing data, and confirm each expected result, including that `LOG_FORMAT=xml` refuses to start and that the waiting-snapshot record doesn't repeat on the 5-minute check.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies. T001 must finish before any code imports structlog.
- **Foundational (Phase 2)**: Depends on T001. T004→T005 and T006→T007→T008 are sequential chains; the two chains can run in parallel. This phase blocks both user stories.
- **US1 (Phase 3)**: Depends on Phase 2.
- **US2 (Phase 4)**: Depends on Phase 2, and on US1's T012–T013 (the pipeline wired into `main.py` and the `request completed` record that T022 extends). US2's tests (T016–T021) can be written while US1 is in progress.
- **Polish (Phase 5)**: Depends on US1 and US2.

### Within Each Story

- Tests are written first and must fail. Then the implementation tasks follow, in ID order.
- Tasks that edit the same file run in sequence:
  - `backend/src/main.py`: T012 → T013 → T014 → T022 → T023 → T024;
  - `backend/tests/contract/test_request_logging.py`: T010 → T016;
  - `backend/tests/unit/test_logging_config.py`: T006 → T009;
  - `backend/src/logging_config.py`: T007 → T011.
- `EXPECTED_REPORT` in T021 must be captured from the code as it is before T028 changes it.

### Parallel Opportunities

- Setup: T002 and T003.
- Foundational: T004 and T006, both test files.
- US1: T009 and T010.
- US2 tests: T016, T017, T018, T019, T020 and T021 are all in different files.
- US2 implementation: T025 (`active_snapshot.py`), T026 (`icon_coverage.py`), T027 (`sku_selections.py`) and T028 (the generator script) are in different files and can run in parallel with the `main.py` chain (T022–T024).
- Polish: T029 and T030.

---

## Parallel Example: User Story 2

```bash
# All US2 tests at once (different files):
Task: "T016 Request-ID tests in backend/tests/contract/test_request_logging.py"
Task: "T017 Snapshot event tests in backend/tests/unit/test_active_snapshot.py"
Task: "T018 Icon coverage event tests in backend/tests/unit/test_icon_coverage.py"
Task: "T019 Move event tests in backend/tests/contract/test_sku_selections.py"
Task: "T020 Secrets test in backend/tests/contract/test_log_secrets.py"
Task: "T021 Generator tests in backend/tests/unit/test_icon_map_generator_log.py"

# Then the implementation, in parallel with the main.py chain T022→T023→T024:
Task: "T025 Snapshot events in backend/src/pricing_data/active_snapshot.py"
Task: "T026 Icon coverage events in backend/src/pricing_data/icon_coverage.py"
Task: "T027 Move events in backend/src/api/sku_selections.py"
Task: "T028 --log-file in backend/scripts/generate_aws_service_icon_map.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup (T001–T003).
2. Phase 2: Foundational (T004–T008).
3. Phase 3: US1 (T009–T015).
4. **Stop and validate**: quickstart.md §2 and §4. Every line is JSON, there is one request line per request, and the console format works.

### Incremental Delivery

1. Setup + Foundational: the pipeline exists and is tested in isolation.
2. US1: the whole backend writes JSON. This is the MVP, and it is deployable as is.
3. US2: request IDs, then the snapshot and icon events, the move events, the secrets check and the generator `--log-file`. Each one can be merged on its own once its test passes.
4. Polish: fix the docs, run the leftover-logging search, and do the full quickstart run.

---

## Notes

- [P] tasks touch different files and don't depend on unfinished tasks.
- Commit after each phase, or after each logical group within US2.
- The `message` strings and field names are a contract (contracts/log-format.md §2). Tests assert them exactly, so don't reword them.
