# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

This is a multi-service workspace. The **active project is `Intelligent-Audio-TEST/`** — a Flask + Vue/Electron platform for automated testing and evaluation of audio/AI devices (ASR, translation, voice-LLM). The whole workspace is **one git repository rooted at `D:/work/20260630`** (remote `ydz-auto/intelligent_audio_test.git`); `Intelligent-Audio-TEST/` is a subdirectory, so git commands resolve to the same outer repo whether run from the workspace root or from inside `Intelligent-Audio-TEST/`.

Sibling directories are **standalone services** (separate code, not imported by the main app):
- `eval_server/` — Flask evaluation server (port 5001, waitress). Computes WER/SER/DER/llm_judge metrics on ASR/translation outputs. The main app's evaluation service calls it as an external HTTP endpoint.
- `api_adaper_service/` (sic) — Flask WebSocket frame-streamer to Volcano Engine ASR (port 8000). Older standalone design.
- `audio_intelligence/` — not a server; a daily batch job (`run_daily.py`) that builds a competitive-intel HTML report and emails it. Unrelated to the test platform.

Inside the main app, `Intelligent-Audio-TEST/api_adapter_service/` (correctly spelled) is **different** from the sibling `api_adaper_service/`: it's an HTTP REST adapter for multi-round voice-LLM dialog, called by the backend's API executor, packaged as `api_adapter_service.*` (port 8000).

## Common commands

Backend (run from `Intelligent-Audio-TEST/`):
```bash
python run.py                    # Flask + SocketIO on :5000 (FLASK_CONFIG env: default|development|production|testing)
python start_postgres.py         # start bundled PostgreSQL (default: localhost:5432, db/user "intelligent_audio_test")
python stop_postgres.py          # stop it
```
Tables auto-create on startup via `db.create_all()` from the SQLAlchemy models; Flask-Migrate/Alembic migrations live in `backend/scripts/migrations/`.

Frontend (run from `Intelligent-Audio-TEST/frontend/`):
```bash
npm run dev          # Vite dev server on :5173, proxies /api → localhost:5000 (override via VITE_API_TARGET)
npm run electron:dev # run inside Electron shell (loads :5173 in dev, dist/ in prod)
npm run build        # vite build → dist/
npm run type-check   # vue-tsc --noEmit
npx vitest           # frontend tests (watch). No "test" npm script; invoke vitest directly.
npx vitest run src/composables/__tests__/useAlgorithmConfig.spec.ts   # single test file
```
Vitest config is inside `vite.config.ts` (`test.include = src/**/__tests__/**/*.spec.ts`). Vite alias: `@` → `src/`.

Backend tests (run from `Intelligent-Audio-TEST/`):
```bash
pytest backend/tests/                                          # all
pytest backend/tests/test_algorithm_params.py                  # one file
pytest backend/tests/test_algorithm_params.py::test_function   # one test
```
**Backend tests require a live PostgreSQL** — `backend/tests/conftest.py` builds the app with the `testing` config and isolates each test with a real DB + nested SAVEPOINT transactions (rolled back, not committed). Known limitation: controller code that calls `db.session.commit()` truly commits and can cause `UniqueViolation` across tests, so run algorithm tests **individually** rather than as a suite.

Config is loaded from `backend/config/.env` (falls back to `backend/.env`, then `Intelligent-Audio-TEST/.env`). See `backend/.env.example` for all knobs (DB creds, ffmpeg/ffprobe paths, executor pool sizes, scheduler interval). `ffmpeg.exe`/`ffprobe.exe` are required (pydub/librosa) — set `FFMPEG_PATH`/`FFPROBE_PATH` or it falls back to a hardcoded path then `PATH`.

## Architecture

### Backend (Flask app factory)
`backend/app.py` `create_app()` is the factory. The request lifecycle is layered with **cross-cutting middleware applied at the factory level**:
1. `NamingRequest` (replaces `app.request_class`) — every inbound JSON body is normalized to **snake_case**.
2. `NamingAliasMiddleware` (wraps `wsgi_app`) — query-string params are duplicated in both snake_case and camelCase.
3. `before_request`/`after_request` — log every request/response (elapsed ms, security headers) via `log_and_emit`.
4. Global `errorhandler` wraps all exceptions into the unified `ApiResponse` format.

**Layered routing:** `backend/blueprints/*_bp.py` (URL routing, prefix `/api/v1/<resource>`) → `backend/controllers/*_controller.py` (orchestration + business logic) → `backend/services/` (work) → `backend/models/` (SQLAlchemy ORM) + `backend/schemas/` (Pydantic v2 DTOs). Blueprints stay thin; controllers hold the logic.

### snake_case ↔ camelCase bridge (important)
The backend works entirely in **snake_case** (Python models, controllers, DB). The API surface is **camelCase** for the frontend:
- **Responses:** `success_response` / `error_response` (`backend/utils/web/response.py`) recursively convert snake_case keys to camelCase; Pydantic schemas serialize with `by_alias=True, exclude_none=True`.
- **Requests:** `NamingRequest` + `NamingAliasMiddleware` convert inbound to snake_case, so controllers always read snake_case regardless of what the client sent.
- The frontend has matching helpers in `src/utils/fieldNaming.ts` (`snakeToCamelObject`, `camelToSnakeObject`, alias-tolerant `getFieldWithAliases` / `normalizeReport`) because some payloads still arrive in mixed cases. When adding fields, define them snake_case in the model/schema and they will be emitted camelCase automatically.

### Unified API shape
`backend/schemas/response.py` `ApiResponse` + `backend/utils/web/error_codes.py` `ErrorCode`. Success → `{success:true, code, message, data}`; errors add `detail`. Always return via `success_response`/`error_response`, never raw `jsonify`.

### Execution engine (how a test runs) — `backend/services/execution/`
`ExecutionEngine` is a singleton (`execution_engine`) started in `create_app`. It owns:
- A scheduler daemon thread polling `Task` rows with `status='pending'` every `scheduler_interval` (default 3s, event-woken).
- A `task_queue` (deque, cap 100); one OS `threading.Thread` per running task (`workers[task_id]`).
- Per-task control flags (`stop_flags`, `pause_flags`) registered globally so **device drivers** can cooperatively stop/pause mid-operation (`BaseDeviceDriver._check_stop`).
- Three shared `ThreadPoolExecutor`s: `api_task_pool`(10), `device_control_pool`(5), `audio_playback_pool`(3), plus a per-task API pool sized by the sum of online endpoints' `max_process`.
- Concurrency rules: E2E tasks are mutually exclusive (`running_e2e`); API tasks run concurrently but never share the same API (`running_apis`).

Two case executors: `E2EExecutor` drives real devices through the driver factory + playback orchestrator + `device_result_collector`; `APIExecutor` hits HTTP endpoints (e.g. the bundled `api_adapter_service`). After execution, `BaseExecutor._evaluate_result` hands off to evaluation.

**State machine:** `Task.status` `pending→queued→running→(paused)→completed|failed|stopped`. `TaskCase` has separate `execution_status` and `evaluation_status` (each `pending→queued→running→…`); the rollup `TaskCase.status` is set only after **both** resolve. On server restart, `create_app` sweeps all in-flight tasks/cases/results to `failed`.

### Evaluation — `backend/services/evaluation/evaluation_service.py`
`EvaluationService` (singleton) loads `Dimension` config, groups dimensions by `(endpoint_url, task_type)`, and dispatches each group to an `EndpointWorker` (own `queue.Queue` + N consumer threads, N = endpoint `max_process`). It POSTs to an external eval API (the `eval_server`) with failover/fallback, then `EvaluationResultProcessor` extracts raw values (via `EvaluationDimensionParam.field_path` or `response_mapping`) and applies scoring rules (`direct`/`linear`/`threshold`) into `TestResultDimension`.

### Real-time (SocketIO)
`socketio` (`async_mode='threading'`) is created in `backend/app.py` and shared app-wide. The engine's `EventManager` emits `task_progress` (throttled, force-emitted on state/round change) and `error_alert`. The DB-backed log handler (`backend/utils/web/log_handler.py`, used everywhere via `log_and_emit` / `driver._log`) streams `logs`/`task_log` to namespace `/ws/logs`. Because `async_mode='threading'`, background worker threads emit directly — no Celery, no task queue broker.

### Device drivers — `backend/utils/device_driver/`
`DeviceDriverFactory` selects a driver by **OS + keyword matching**. Base drivers (`AndroidDriver` via adbutils/uiautomator2, `HarmonyDriver` via `hdc` subprocess) handle generic devices; specialized drivers (`PlaudDriver`, `XiaoyiFace2FaceDriver`, `XiaoyiSimultaneousInterpretationDriver`, `HarmonyHardenXiaoyiHuiJiDriver`) are registered with keyword lists (e.g. `['plaud','ai录音']`) and selected when a device's keywords match. All drivers extend `BaseDeviceDriver` (`initialize`/`pre_process`/`post_process`/`get_results`/`set_volume`…) and support a `mock_mode` (every step returns `True`) for testing without hardware. To add a device type, subclass `BaseDeviceDriver` and `register_specialized_driver(...)` in the factory.

### Domain model — `backend/models/models.py` (~45 tables)
Core entities: `Task` → `TaskCase` (a test case within a task) + `TaskDevice`/`TaskAPI`/`TaskTag`; `TestCase`/`TestCaseGroup`; `Device`/`PlaybackDevice`; `Audio`/`AudioAnnotation` (multi-round uploads); `TestResult` + `TestResultDimension`; `Report` + many `Report*` aggregates; `Dimension`/`Category` (evaluation config); `Tag`/`TagCategory` (polymorphic tags across cases/devices/audios); `SPLMapping`/`CalibrationHistory`. Algorithm params/definitions live in `backend/models/algorithm_models.py`. Most models use `utc8now()` for timestamps (UTC+8 throughout — logs, timestamps, the `UTC8Formatter`).

### Frontend (Vue 3 + Pinia + Electron)
- Hash-history router (`src/router/index.ts`) maps to `src/views/*.vue`. Each view is split into a thin `.vue` + a **`<View>Logic/` folder** (e.g. `Tasks.vue` + `TasksLogic/`) holding extracted sub-components and a `.ts` logic module. Stateful logic lives in `src/composables/use*.ts` composables (the bulk of the behavior). Pinia stores are in `src/store/`. API client types in `src/utils/api.ts`.
- In Electron, renderer requests go through the preload IPC bridge (`electron-main.ts` `api-request` handler → axios to `127.0.0.1:5000`), so the backend is expected to run locally even in the desktop build.
- New feature pattern: add route → `views/X.vue` + `views/XLogic/` → composables in `composables/` → backend blueprint/controller/service.

## Conventions / gotchas
- **Always operate in snake_case inside the backend.** The request/response layers convert cases; do not manually camelCase in controllers or models.
- Return responses through `success_response`/`error_response` with an `ErrorCode`; never build the envelope by hand.
- Time is **UTC+8** everywhere (`utc8now()`, `UTC8Formatter`).
- Code comments and UI strings are predominantly **Chinese**; match the surrounding language.
- Heavy device/audio operations run on background threads — when adding driver/exec logic, thread the per-task `stop_event`/`pause_event` through and call `_check_stop()` at natural points so tasks remain stoppable/pausable.
- `JSON_AS_ASCII=False` is set so Chinese is emitted directly — don't re-escape it.
