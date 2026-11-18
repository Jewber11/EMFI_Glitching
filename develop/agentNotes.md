# Agent Notes — Develop App

Notes from the audit and build-out sessions against the Develop scaffold.

## Session 1: Scaffold Audit (2026-05-26)

### What was audited
Walked through `SPEC.md` section-by-section, cross-referencing the plan file
(`i-am-looking-for-wiggly-quill.md`), `../ARCHITECTURE.md`, and every file in
`protocol/`.

### Gaps found and fixed

**[missing] — Git endpoints had no HTTP surface**
`git_ops.py` existed with `commit`, `tag`, `log` functions, but no router
exposed them. Created `routers/git.py` with:
- `POST /projects/{id}/git/commit`
- `POST /projects/{id}/git/tag`
- `GET  /projects/{id}/git/log`

**[missing] — `GET /templates` endpoint**
The spec lists a templates endpoint; no router existed.
Created `routers/templates.py`.

**[missing] — `frontend/src/lib/stores/` directory**
The plan file lists this directory in the scaffold tree but it was never
created. Added `stores/index.ts` placeholder.

**[drift] — Build trigger path was plural**
Spec says `POST /projects/{id}/build` (singular). Scaffold had
`POST /projects/{id}/builds` (plural, via router prefix). Fixed by removing
the prefix from the builds router and using explicit full paths so the
trigger is singular and list/get remain plural.

### Extra endpoints (kept, flagged)
`routers/artifacts.py` has `firmware.bin` and `firmware.lst` download
endpoints not in SPEC.md. These are useful since the build outputs include
those files. Recommend adding to spec or removing if strict spec compliance
is desired.

### Verification results
- `python3 -m py_compile` on all `.py` files: PASS
- `npx svelte-check`: PASS (0 errors, 0 warnings)
- Node.js installed via Volta; had to run `npx svelte-kit sync` first to
  generate `.svelte-kit/tsconfig.json`

---

## Session 2: Logging & start.sh (2026-05-26)

### Problem
Zero logging existed anywhere in the backend. No startup script.
Diagnosing runtime issues would require adding print statements after the
fact — not tenable for a lab service.

### What was added

**`backend/develop/logging_config.py`** — centralized setup:
- Configures root logger with both console (stdout) and rotating file handler
- File handler: 10 MB max, 5 backups, written to `./logs/develop.log`
- Env vars: `EMFI_LOG_LEVEL` (default INFO), `EMFI_LOG_DIR` (default `./logs`)
- Format: `timestamp | LEVEL | module | message`
- Quiets `uvicorn.access` to WARNING to avoid double-logging HTTP requests
  (we log them with timing in our own middleware instead)

**Request logging middleware** (`main.py`):
- Logs every HTTP request with method, path, status code, and elapsed time in ms
- Gives a single clean line per request for easy grep

**Lifecycle logging** (`main.py` lifespan):
- Logs on startup: log file path, projects root, templates root, frontend status
- Logs on shutdown

**Per-module loggers** — every backend module and router now has:
```python
import logging
log = logging.getLogger(__name__)
```
With appropriate log calls:
- `log.info` for state-changing operations (create, delete, build, commit, agent launch)
- `log.warning` for destructive operations (delete project, remove target)
- `log.debug` for read-only/frequent operations (list, get, tree)

**`start.sh`** — startup script:
- Starts uvicorn on port 8002 (configurable via `--port`)
- `--debug` flag sets log level to DEBUG
- `--reload` flag enables uvicorn hot-reload for development
- Creates timestamped session log: `logs/develop-YYYYMMDD-HHMMSS.log`
- Symlinks `logs/latest.log` to the current session
- Uses `tee` to display output in terminal AND save to file simultaneously
- Prints a startup banner with port, log level, log file path, projects root
- Respects `EMFI_LOG_LEVEL`, `EMFI_LOG_DIR`, `EMFI_PROJECTS_ROOT` env vars

### Log file locations
```
develop/
  logs/
    develop.log              # rotating file from Python's RotatingFileHandler
    develop-20260526-183000.log  # session log captured by start.sh via tee
    latest.log → develop-20260526-183000.log  # symlink to current session
```

Two complementary log sinks:
1. `develop.log` — the Python handler's rotating log, always active regardless
   of how the service is started (direct uvicorn, start.sh, etc.)
2. `develop-<timestamp>.log` — full stdout/stderr capture from start.sh,
   includes uvicorn's own output too

### Design decisions
- Used Python stdlib `logging` rather than structlog/loguru — zero new deps,
  matches the existing stack
- Rotating file handler rather than daily rotation — prevents a runaway build
  log from filling the disk
- Request timing in middleware rather than uvicorn access log — gives us
  control over format and lets us add request IDs later without changing
  uvicorn config
- Session log files are append-only and never deleted by the script — the
  user decides when to clean up

---

## Session 3: Full Implementation (2026-05-27)

### What was implemented

All `NotImplementedError` stubs replaced with working logic. Every 501 endpoint
now returns real data or meaningful errors.

#### Backend modules (all under `backend/develop/`)

**`projects.py`** — full CRUD:
- `list_projects()` scans `~/emfi-projects/`, reads `project.toml` via `tomllib`
- `create_project()` copies template, renders `project.toml.template`, git init + commit
- `delete_project()` soft-deletes to `.trash/`
- `file_tree()` recursive dir walk (skips `.git`, `builds`)
- `read_file()` / `write_file()` with path-traversal prevention
- Custom exceptions: `ProjectNotFoundError`, `ProjectExistsError`

**`git_ops.py`** — all via subprocess:
- `commit()` — `git add -A` then `git commit`, returns SHA
- Detects "nothing to commit" gracefully
- `log_entries()` uses null-byte delimited format (safe against quotes in messages)
- Sets user.email/user.name on `init()` for lab-box repos

**`targets.py`** — JSON file CRUD with auto-commit

**`builds.py`** — async build pipeline:
- Reads `project.toml` for language, dispatches to `make` or `cargo`
- `compute_sha()` hashes source tree + toolchain version strings
- Caches builds: if `builds/<sha>/` exists, returns cached artifact
- `_collect_artifacts()` copies ELF/BIN/LST into build dir
- Writes `build_meta.json` for metadata retrieval
- Graceful `ToolchainNotFoundError` if gcc/cargo not on PATH → 503
- Streams build output via broadcaster (BUILD_LOG, BUILD_STATUS topics)

**`disassemble.py`** — objdump parser:
- Regex state machine: function headers, instructions, source annotations
- `disassemble_cached()` caches parsed result as `disassembly.json`

**`agent.py`** — async subprocess:
- Spawns `claude --print <prompt>` in project dir
- Streams output via broadcaster (AGENT_OUTPUT topic)
- Graceful error if Claude CLI not installed

**`broadcaster.py`** — new module:
- Module-level singleton `broadcaster`
- Topic-based pub/sub for WebSocket clients
- Dead client cleanup on send failure

#### Routers

All wired to real backend modules with proper HTTP error codes:
- 404 for missing project/build/file
- 409 for duplicate project/target
- 503 for missing toolchain
- `routers/projects.py` — `put_file` changed from query param to `PutFileRequest` body model
- `routers/templates.py` — scans template dirs, reads language/hal from toml template

#### Frontend (all under `frontend/src/`)

**Infrastructure:**
- `vite.config.ts` — fixed proxy: `/projects`, `/templates`, `/ws` → backend
- `types.ts` — added `BuildArtifact`, `GlitchTarget`, `WsEvent`, `FileTreeNode`, `Template`, `GitLogEntry`
- `api.ts` — complete typed client for all endpoints, including `flashToTarget` (calls Control)
- `ws.ts` — reconnecting WebSocket class with topic subscription and exponential backoff
- `stores/index.ts` — Svelte stores for build log, status, agent output, targets

**Components:**
- `MonacoEditor.svelte` — dynamic import, vs-dark theme, language detection, Ctrl-S save
- `ProjectTree.svelte` — recursive tree with expand/collapse, file selection events
- `BuildLog.svelte` — auto-scroll, ANSI strip, 10k line cap
- `AssemblyView.svelte` — instruction table with target highlighting, click-to-select

**Pages:**
- `/` — project list as card grid, create form with template dropdown, delete with confirmation
- `/projects/[id]` — 3-panel editor: file tree | Monaco | console. Git controls (commit/tag),
  agent prompt, build button, flash button, tabbed console (build log / agent / git log)
- `/projects/[id]/asm` — build selector, assembly table, target sidebar, add-target dialog

**Layout:** clean nav with breadcrumbs, dark header

### Pre-implementation fixes applied
1. Vite proxy changed from `/api` to specific route prefixes
2. Build POST URL fixed from plural to singular in api.ts
3. `put_file` changed from query param to request body

### Verification
- `python3 -m py_compile` on all `.py` files: **PASS**
- `npx svelte-check`: **0 errors, 0 warnings**

### What needs Control for full operation
The "Flash" button calls `POST http://localhost:8001/target/flash` with:
```json
{"elf_url": "http://...:8002/projects/{id}/builds/{sha}/firmware.elf", "build_sha": "..."}
```
Control needs this endpoint to download the ELF and flash via XDS110.

### What needs toolchains for full operation
- `arm-none-eabi-gcc` + `make` for C builds
- `cargo` + `thumbv8m.main-none-eabi` target for Rust builds
- `arm-none-eabi-objdump` for disassembly
- `claude` CLI for agent endpoint

All fail gracefully with 503 + descriptive message if not installed.
