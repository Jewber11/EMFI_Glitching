# Control App — Agent Notes

Notes from the audit and build-out sessions on this app.

---

## Audit Summary (Session 1)

Walked SPEC.md section-by-section against the scaffold. State before fixes:

### What was present and correct
- All 8 spec'd REST endpoint groups exist as router stubs (devices, motion, shouter, target, campaigns, runs, safety, ws).
- All 5 seed modules (safety, workers, state, logbook, ports) are faithful ports of the old carry-forward code.
- Orchestrator stub has correct signatures for `perform_attempt`, `run_campaign`, `replay`.
- All 4 HANDOFF.md carry-forward bugs are addressed or documented at the correct location:
  - `Scaffold.bus.ser.close()` fragile → TODO in `adapters/scaffold.py`
  - `wait_for_arm()` infinite block → timeout parameter in `adapters/chipshouter.py`
  - `arm()` idempotent → docstring + signature in `adapters/chipshouter.py`
  - `sys.path` injection → replaced by `control.adapters` package
- SQLite schema in `logbook.py` matches SPEC.md exactly.
- All 5 test files present; 21 pass, 4 skipped (orchestrator stubs).
- pyproject.toml declares all required deps.
- Protocol models (`emfi_protocol`) match what the routers import.

### What was missing and added
| Item | Fix |
|------|-----|
| `control.tools.reindex` — SPEC says `python -m control.tools.reindex` for SQLite rebuild | Created `src/control/tools/{__init__,__main__,reindex}.py` |

### What had drift and was resolved
| Item | Drift | Fix |
|------|-------|-----|
| `config.py` | SPEC says "hot reload" + "mirrors old config shape"; scaffold had bare `load()`/`save()` functions | Rewrote as `Config` class with `load`, `save`, `snapshot`, `update`, `get` — matching old carry-forward |
| `adapters/base.py` | SPEC says common interface is `(connect, disconnect, status)`; scaffold only had `connected` property | Added `status()` method returning `{name, connected, port, last_error}` |

### Flagged for user
- `POST /target/debug_detach` exists in `routers/target.py` but is not in SPEC.md. It is functionally needed to stop the OpenOCD process started by `debug_attach`. Consider adding to SPEC.md.

---

## Logging & Startup (Session 2)

### Problem
The scaffold had almost zero logging infrastructure:
- Only `orchestrator.py` and `workers.py` created a `LOGGER`.
- No log configuration — no format, no file handler, no rotating logs.
- No `start.sh` or any startup script.
- The old codebase (`old-em-setup/glitchweb/`) had proper logging to both console and a rotating file at `~/.local/state/glitchweb/logs/server.log` with 5MB×5 backups.

### What was added

**Logging configuration** (`main.py`):
- `setup_logging()` configures the root logger with both a `StreamHandler` (console) and a `RotatingFileHandler` (file).
- Log file: `~/.local/share/emfi-control/logs/control.log` (10MB × 5 backups).
- Overridable via `CONTROL_LOG_DIR` env var.
- Format: `2026-05-26 14:30:00 INFO     control.safety: ARM gate ENGAGED`
- Uvicorn access log demoted to WARNING to reduce noise.
- HTTP request/response middleware logs all requests and warns on 4xx/5xx.
- Runs as part of FastAPI lifespan — logging is configured before the first request.

**Per-module loggers added** to every module that was missing one:
- `safety.py` — logs arm/disarm transitions, auto-disarm events, blocked pulses, rate-limit hits
- `state.py` — logs WS client register/unregister
- `logbook.py` — logs session open, append operations, listener errors
- `config.py` — logs config load/create, parse failures
- `ports.py` — logs port scan results
- `adapters/chipshover.py`, `chipshouter.py`, `scaffold.py`, `xds110.py` — logger ready for build-out
- `routers/ws.py` — logs WS connect/disconnect with client address

**`start.sh`**:
- Creates/activates a `.venv` automatically on first run.
- Installs `../protocol` and the control package with dev deps.
- Supports `--reload` (for dev) and `--debug` (DEBUG-level logging).
- Prints a startup banner with service URL, log file path, and PID.
- Exports `CONTROL_HOST`, `CONTROL_PORT`, `CONTROL_LOG_DIR` for `main.py`.
- Uses `exec` so the uvicorn process replaces the shell (clean signal handling).

### Log locations
```
~/.local/share/emfi-control/logs/control.log      # rotating server log (10MB × 5)
~/.local/share/emfi-control/sessions/              # JSONL logbook (canonical data)
~/.config/emfi-control/config.json                 # persistent config
```

---

## Endpoint Wiring (Session 3)

### Problem
All router endpoints were 501 stubs. View and Develop apps need real working endpoints — WS streaming, REST for devices/motion/shouter/campaigns/runs/safety, and `POST /target/flash` with scaffold-power-on-before-flash semantics.

### What was added

**`src/control/deps.py`** (NEW) — central application context:
- `AppContext` dataclass holding all shared singletons: Config, AppState, Broadcaster, ArmGate, StopFlag, RateLimiter, Logbook, WorkerRegistry, all 4 adapters, Orchestrator, in-memory campaigns dict
- `build_context()` factory — instantiates everything in order, wires `arm_gate.on_change` to update state + broadcast `arm` topic
- `broadcast(topic, payload)` helper — uses `broadcast_threadsafe` when called from device worker threads
- `get_ctx(request)` — FastAPI `Depends` helper for all routers
- `call_adapter(worker, fn, ...)` — runs fn on DeviceWorker, catches `NotImplementedError` → 501
- `call_subprocess_adapter(fn, ...)` — same for XDS110 (no DeviceWorker, uses `run_in_executor`)

**`main.py`** updated:
- Lifespan creates `AppContext` via `build_context()`, stores on `app.state.ctx`, captures `asyncio.get_running_loop()` for thread-safe broadcasting
- Shutdown path: `stop_flag.set()`, disconnect all adapters safely, `workers.shutdown_all()`
- Global exception handlers: `Disarmed` → 403, `RateLimited` → 429, `NotImplementedError` → 501

**All 8 routers wired** — no more 501 stubs for logic that doesn't need hardware:

| Router | Endpoints | Notes |
|--------|-----------|-------|
| `safety.py` | `POST /arm`, `POST /disarm`, `GET /arm_state` | Fully working, returns `ArmState` model |
| `ws.py` | `WS /ws` | Full broadcaster binding, initial state snapshot, ping/subscribe support |
| `devices.py` | `GET /devices`, `POST /{name}/connect`, `POST /{name}/disconnect` | Port scan works; connect/disconnect call adapters via workers |
| `motion.py` | `POST /move_abs`, `/move_rel`, `/home`, `/set_origin`, `/set_top_right` | `set_top_right` is pure state (works now); others hit adapter stubs → 501 |
| `shouter.py` | `POST /arm`, `/disarm`, `/pulse`, `/config` | Pulse enforces arm gate (403) + rate limiter (429) before adapter call |
| `target.py` | `POST /flash`, `/reset`, `/debug_attach`, `/debug_detach` | Flash sequence: scaffold `dut_power_cycle()` → XDS110 `flash(elf_path)` |
| `campaigns.py` | `POST /campaigns`, `GET /campaigns`, `GET /{id}`, `POST /{id}/stop` | In-memory campaign store, background task for orchestrator |
| `runs.py` | `GET /runs`, `GET /{id}`, `GET /heatmap`, `POST /replay/{run_id}` | Logbook queries work; replay enforces arm gate |

**`adapters/chipshover.py`** — added missing stubs: `home()`, `set_origin()`, `move_relative()`

### What works without hardware
- ARM/disarm cycle with auto-disarm countdown
- WS connection with full state snapshot on connect + live broadcasts
- Device listing with port scan
- Campaign create/list/get/stop (orchestrator runs as background task, catches NotImplementedError)
- Logbook queries (runs, heatmap) from SQLite mirror
- `set_top_right` (pure state operation)
- Proper error responses: 403 for disarmed, 429 for rate limited, 501 for unimplemented adapters, 404 for not found

### Flash endpoint sequence
`POST /target/flash { build_sha, elf_url }`:
1. Scaffold worker: `dut_power_cycle()` — powers on the DUT board
2. Resolve ELF: supports `file://` (local path) and `http://` (download from Develop)
3. XDS110: `flash(elf_path)` via `run_in_executor` (subprocess, not DeviceWorker)
4. Currently returns 501 because `ScaffoldAdapter.dut_power_cycle()` is a NotImplementedError stub

---

## Architecture Notes

### What still needs build-out (V1 scope, stubs exist)
These are all `raise NotImplementedError` stubs that the build-out session should fill in:

1. **Orchestrator** — `perform_attempt()`, `run_campaign()`, `replay()`. Reference: `old-em-setup/glitchweb/backend/app/orchestrator.py` lines 49-222.
2. **All adapter `.connect()` / `.disconnect()` and device-specific methods** — each wraps the upstream pip library (chipshover, chipshouter, donjon-scaffold) or a subprocess (openocd, dslite).

### What is Phase 2 (deferred, do NOT implement)
- USB webcam overlay + optical calibration
- Continuous background heartbeat watcher coroutine
- Delta-encoded WS state broadcasts
- Cross-rig comparison / cloud archive
- AWS S3 / Azure Blob nightly logbook backup

---

## ChipShoverAdapter Implementation (Session 4)

### Problem
`adapters/chipshover.py` was all `NotImplementedError` stubs. Every motion endpoint returned 501. The `agentConversation.md` block entry identified this as a concrete blocker for View's JogPad.

### What was implemented

**`adapters/chipshover.py`** — full implementation wrapping the `chipshover` pip library:

| Method | Implementation |
|--------|---------------|
| `connect(port)` | `ChipShover(port)`, reads initial position |
| `disconnect()` | `self._impl.close()`, clears state |
| `get_position()` | Returns machine `(x, y, z)` from library |
| `get_position_logical()` | Machine pos minus origin offset |
| `move_absolute_logical(x, y, z)` | Translates via `_origin_machine`, calls `self._impl.move(mx, my, mz)` |
| `move_relative(axis, distance)` | Reads current pos, adds delta, calls `move()` |
| `home()` | `self._impl.home()`, clears origin |
| `set_origin()` | Records current machine position as `_origin_machine` |

Logical↔machine coordinate translation ported from `old-em-setup/glitchweb/backend/app/devices/chipshover_dev.py:92-104`.

**Startup auto-connect** (`main.py`):
- `_auto_connect()` runs in the lifespan after context build
- Connects any device that has a pinned `ports.*_override` in config
- Failures are logged but don't block startup
- On the lab box with pinned `/dev/ttyACM0`, ChipShover auto-connects at boot

**Motion router** (`routers/motion.py`):
- Updated to read back actual position from adapter after every move (`_refresh_position()`)
- Updates both `position_machine` and `position_logical` in state

**Error handling** (`deps.py`):
- `call_adapter()` now catches `RuntimeError` and `ValueError` from adapters → 500 with clear message
- "ChipShover is not connected" → 500 (hardware absent)
- "Adapter not implemented" → 501 (stub methods on other adapters)

**Config defaults** (`config.py`):
- Added Marlin-based classifier patterns (`manufacturer_contains: marlinfw`, `description_contains: 3D Printer`) since the lab box's ChipShover runs Marlin, not Smoothie

### Current error behavior per adapter
| Adapter | Status | Error on call |
|---------|--------|--------------|
| ChipShover | **Implemented** | 500 "not connected" (no hardware) or works (lab box) |
| ChipSHOUTER | Stub | 501 "not implemented" |
| Scaffold | Stub | 501 "not implemented" |
| XDS110 | Stub (except `detach_debugger`) | 501 "not implemented" |

### Key invariants to preserve
1. All hardware calls go through `DeviceWorker` (single-thread-per-device executor).
2. All pulse-emitting paths call `arm_gate.require_armed()` then `rate_limiter.acquire()`.
3. JSONL logbook is canonical; SQLite is a rebuildable mirror.
4. State mutations broadcast via `Broadcaster`.
5. One process per rig (serial devices have exclusive open semantics).

### Test strategy
- Pure-Python modules tested without hardware: safety, workers, state, logbook.
- Orchestrator tests use fake adapters (in-memory, no hardware).
- Hardware tests marked `@pytest.mark.hw`, skipped by default.
- Run all: `pytest tests/` (from the control/ dir or via `start.sh` with the venv active).

### Environment
- Python 3.11+ required (tested on 3.14.4).
- pyproject.toml uses `src/` layout — `control` package lives at `src/control/`.
- Protocol installed as editable dep: `pip install -e ../protocol`.
