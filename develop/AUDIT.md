# Develop — Scaffold Audit Report

Audited against: `SPEC.md`, `../ARCHITECTURE.md`, plan file `i-am-looking-for-wiggly-quill.md`.

## REST Endpoints

| Spec endpoint | Status | Scaffold location |
|---|---|---|
| `GET /projects` | [present] | `routers/projects.py:23` |
| `POST /projects` | [present] | `routers/projects.py:28` |
| `GET /projects/{id}` | [present] | `routers/projects.py:33` |
| `DELETE /projects/{id}` | [present] | `routers/projects.py:38` |
| `GET /projects/{id}/tree` | [present] | `routers/projects.py:43` |
| `GET /projects/{id}/file?path=...` | [present] | `routers/projects.py:48` |
| `PUT /projects/{id}/file?path=...` | [present] | `routers/projects.py:53` |
| `POST /projects/{id}/git/commit` | **[missing]** | no router — `git_ops.py` has logic but no HTTP surface |
| `POST /projects/{id}/git/tag` | **[missing]** | same |
| `GET /projects/{id}/git/log` | **[missing]** | same |
| `POST /projects/{id}/build` | **[drift]** | scaffold: `POST /projects/{id}/builds` (plural) — spec uses singular |
| `GET /projects/{id}/builds` | [present] | `routers/builds.py:25` |
| `GET /projects/{id}/builds/{sha}` | [present] | `routers/builds.py:30` |
| `GET /projects/{id}/builds/{sha}/firmware.elf` | [present] | `routers/artifacts.py:12` |
| `GET /projects/{id}/builds/{sha}/disassembly` | [present] | `routers/disassembly.py:14` |
| `GET /projects/{id}/targets` | [present] | `routers/targets.py:14` |
| `POST /projects/{id}/targets` | [present] | `routers/targets.py:19` |
| `DELETE /projects/{id}/targets/{pc}` | [present] | `routers/targets.py:25` |
| `POST /projects/{id}/agent` | [present] | `routers/agent.py:16` |
| `GET /templates` | **[missing]** | no router at all |

## Extra endpoints (scaffold has, spec doesn't mention)

| Endpoint | Status | Notes |
|---|---|---|
| `GET /projects/{id}/builds/{sha}/firmware.bin` | [extra] | `routers/artifacts.py:17` — useful, propose adding to spec |
| `GET /projects/{id}/builds/{sha}/firmware.lst` | [extra] | `routers/artifacts.py:22` — useful, propose adding to spec |

## WebSocket `/ws`

| Topic | Status | Location |
|---|---|---|
| `build_log` | [present] | `routers/ws.py` docstring + `protocol/ws_events.py` |
| `build_status` | [present] | `routers/ws.py` docstring + `protocol/ws_events.py` |
| `agent_output` | [present] | `routers/ws.py` docstring + `protocol/ws_events.py` |

## Pydantic models (protocol/)

| Model | Status | Location |
|---|---|---|
| `Project` | [present] | `protocol/emfi_protocol/projects.py` |
| `BuildArtifact` | [present] | `protocol/emfi_protocol/projects.py` |
| `AssemblyInstruction` | [present] | `protocol/emfi_protocol/projects.py` |
| `AssemblyListing` | [present] | `protocol/emfi_protocol/projects.py` |
| `GlitchTarget` | [present] | `protocol/emfi_protocol/projects.py` |
| `WsEvent` / `WsTopic` | [present] | `protocol/emfi_protocol/ws_events.py` |

## Backend modules

| Module | Status | Location |
|---|---|---|
| `main.py` | [present] | `backend/develop/main.py` |
| `config.py` | [present] | `backend/develop/config.py` |
| `projects.py` | [present] | `backend/develop/projects.py` |
| `git_ops.py` | [present] | `backend/develop/git_ops.py` |
| `builds.py` | [present] | `backend/develop/builds.py` |
| `disassemble.py` | [present] | `backend/develop/disassemble.py` |
| `targets.py` | [present] | `backend/develop/targets.py` |
| `agent.py` | [present] | `backend/develop/agent.py` |

## Templates

| Template | Status | Contents |
|---|---|---|
| `c_ti_hal/` | [present] | Makefile, src/main.c, linker.ld, project.toml.template, targets.json |
| `rust_b01lers/` | [present] | Cargo.toml, src/main.rs, project.toml.template, targets.json |

## Frontend

| Item | Status | Location |
|---|---|---|
| Route `/` | [present] | `routes/+page.svelte` |
| Route `/projects/[id]` | [present] | `routes/projects/[id]/+page.svelte` |
| Route `/projects/[id]/asm` | [present] | `routes/projects/[id]/asm/+page.svelte` |
| `MonacoEditor.svelte` | [present] | `lib/components/MonacoEditor.svelte` |
| `AssemblyView.svelte` | [present] | `lib/components/AssemblyView.svelte` |
| `BuildLog.svelte` | [present] | `lib/components/BuildLog.svelte` |
| `ProjectTree.svelte` | [present] | `lib/components/ProjectTree.svelte` |
| `api.ts` | [present] | `lib/api.ts` |
| `ws.ts` | [present] | `lib/ws.ts` |
| `stores/` directory | **[missing]** | plan file lists `lib/stores/` — not created |

## Tests

| File | Status | Location |
|---|---|---|
| `test_projects.py` | [present] | `tests/test_projects.py` |
| `test_builds.py` | [present] | `tests/test_builds.py` |
| `test_disassemble.py` | [present] | `tests/test_disassemble.py` |

## Dependencies

- `pyproject.toml`: all required deps present (fastapi, uvicorn, pydantic, pyelftools, emfi-protocol)
- `capstone` correctly in optional extras
- `package.json`: all required deps present (svelte, sveltekit, monaco, openapi-typescript, vite)
- All Python files compile: `python3 -m py_compile` — **PASS**
- Frontend type-check: **SKIPPED** (Node.js not installed on this machine)
- pytest: **SKIPPED** (not installed; all tests are `@skip` anyway)

## Fixes required

1. **[missing]** Add `routers/git.py` with git/commit, git/tag, git/log endpoints
2. **[missing]** Add `routers/templates.py` with `GET /templates`
3. **[drift]** Fix build trigger: `POST /projects/{id}/build` (singular, per spec)
4. **[missing]** Create `frontend/src/lib/stores/` directory
5. **[missing]** Register new routers in `main.py`
