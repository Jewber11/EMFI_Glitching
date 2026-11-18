# develop/ — local setup (deployment-specific)

You are working in the Develop app of a 3-app EMFI research platform. Develop owns **firmware projects, builds, disassembly, glitch-target annotations, and a Claude Code agent endpoint**. It has no hardware and no safety state.

## Where this runs

| | |
|---|---|
| Host | `faultierHost2` at `10.164.9.112` (Kali rolling 2025.4, amd64) |
| User | `stephen` |
| Repo | `/home/stephen/EM-Architecture/` |
| SSH alias | `ssh em-lab` |
| Shared venv | `/home/stephen/EM-Architecture/.venv` (Develop's `start.sh` finds it automatically) |
| Projects on disk | `/home/stephen/emfi-projects/<project-id>/` (created on demand) |
| Service logs | `develop/logs/develop-<timestamp>.log` (with `logs/latest.log` symlink) |
| URL | `http://10.164.9.112:8002/` (UI + REST + WS) |

## Toolchains already installed on the lab box

| Tool | Path / version |
|---|---|
| Python | 3.13.9 (system, `/usr/bin/python3`) |
| ARM C toolchain | `arm-none-eabi-gcc` 14.2.1 (apt) |
| ARM objdump | `arm-none-eabi-objdump` (apt) |
| Rust | `rustc` 1.94.1, `cargo` 1.94.1 — target `thumbv8m.main-none-eabi` is **installed** |
| Git | 2.53.0 |
| Node | 20.19.5, npm 11.13.0 |
| Claude Code CLI | `/home/stephen/.local/bin/claude` (2.1.148) |
| OpenOCD | 0.12.0 (used by Control, not by Develop) |

`start.sh` prepends `~/.local/bin` to `PATH` so `claude` resolves when the agent endpoint shells out.

## Hardware *that the firmware targets* (you don't talk to it)

Control owns the rig; Develop only produces artifacts Control flashes. For reference:

- Target MCU: **MSPM0L2228**
- Controller (XY/Z stage): runs **Marlin** firmware (not Smoothie). G-code dialect mostly compatible; don't assume Smoothie-only commands.
- The `chipshover` Python lib (installed in the shared venv) accepts both.

You shouldn't import any hardware libs from this app. If you find yourself reaching for `chipshouter` or `scaffold` in develop/, you're probably writing in the wrong app.

## How you actually run this app

```bash
ssh em-lab
cd ~/EM-Architecture/develop
bash start.sh                # default 0.0.0.0:8002, INFO logging
bash start.sh --debug        # DEBUG logging
bash start.sh --port 18002   # custom port
bash start.sh --reload       # dev hot-reload
```

`start.sh` was fixed on 2026-05-27 to (a) drop a `${#VAR:-default}` bad-substitution in the banner and (b) discover/create a venv instead of assuming one. Discovery order:

1. Caller-activated `VIRTUAL_ENV`
2. Local `develop/.venv`
3. Shared `../.venv`
4. Create `develop/.venv` from scratch (installs `protocol/` + `develop[extras,dev]`)

The frontend builds via Vite/SvelteKit. For dev hot-reload of the UI specifically:

```bash
cd ~/EM-Architecture/develop/frontend
npm run dev    # serves on :5173, proxies /api → :8002
```

Production: `npm run build` outputs `frontend/build/` which `develop/main.py` mounts via FastAPI StaticFiles at `/`.

## API surface — what's there, what's stubbed

Endpoints all return **501 Not Implemented** right now. Each router's handler logs the call before raising, so you'll see traffic shape in `develop/logs/latest.log` even before implementation.

Implementation priority for V1 (see `SPEC.md` for full contract):

1. **`projects` router** — CRUD over `~/emfi-projects/`, plus tree/file get-put
2. **`builds` router** — invoke `make` for C / `cargo` for Rust; capture artifacts under `builds/<sha>/`; deterministic SHA over source tree + toolchain version
3. **`disassembly` router** — `arm-none-eabi-objdump -d -S` → parse into `AssemblyListing` (use `pyelftools` and/or `capstone`)
4. **`targets` router** — `targets.json` CRUD in the project's git repo
5. **`agent` router** — `asyncio.create_subprocess_exec(claude_bin(), "--print", prompt, cwd=project_dir(id), ...)`, stream output via WS topic `agent_output`
6. **`artifacts` router** — `FileResponse` for elf/bin/lst
7. **WS** — broadcast `build_log`, `build_status`, `agent_output`

## Templates already present

- `backend/develop/templates/c_ti_hal/` — Makefile + `src/main.c` placeholder for MSPM0L2228, linker script stub
- `backend/develop/templates/rust_b01lers/` — Cargo.toml + `src/main.rs` for the b01lers HAL target

Both are skeletons. Real linker scripts and HAL imports are intentionally absent — V1 build-out fills them in.

## Cross-app communication

Append-only `agentConversation.md` at the repo root. Use it when:
- You change a Pydantic model in `protocol/` (Control + View both depend on it)
- You change a WS topic name or envelope (View consumes Develop's WS)
- You change an endpoint path or shape
- You add a new build artifact type or path that Control needs to know about

## Out of scope (Phase 2)

Cross-rig artifact sharing, build caching beyond per-sha, agent loops that span all three apps (e.g. agentic glitch-finder). File ideas, don't implement.

## When in doubt

- `SPEC.md` — authoritative API contract
- `AUDIT.md` — scaffold audit findings from initial pass (good context on what's already triaged)
- `../ARCHITECTURE.md` — system rationale
- `../agentsNotes.md` — durable repo-wide notes for AI sessions
- Carry-forward source in `old-em-setup/glitchweb/backend/app/` (only on the dev Mac, ignored from repo) — useful for "how did the old code do X?" lookups
