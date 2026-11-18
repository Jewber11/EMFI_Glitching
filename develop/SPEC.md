# Develop — Spec

## Purpose

Owns firmware artifacts. Projects, builds, disassembly, glitch-target annotations, and AI-assisted authoring. No hardware. No safety state. Talks to nothing but the filesystem, toolchains, git, and the `claude` CLI.

## Project model

Each project is a directory under `~/emfi-projects/<project-id>/`:

```
~/emfi-projects/glitch_target_v3/
  project.toml              name, language, target, hal, created_at, description
  src/                      firmware source (Makefile / Cargo.toml at root)
  targets.json              GlitchTarget annotations (PC → metadata)
  .git/                     versions = git tags (v0.1.0, v0.2.0, ...)
  builds/<sha>/             deterministic build outputs
    firmware.elf
    firmware.bin
    firmware.lst            arm-none-eabi-objdump -d output
    symbols.json            symbol table + source mapping
    build.log
```

`project.toml`:
```toml
name = "Glitch Target v3"
language = "c"            # c | rust
target = "mspm0l2228"
hal = "ti"                # ti | b01lers
created_at = "2026-05-26T18:00:00Z"
description = "Optional"
```

The build SHA is deterministic over `(source tree + toolchain versions)` so Control can pin a campaign to an exact artifact.

## Toolchains

| Language | HAL | Compiler | Build command |
|---|---|---|---|
| C | TI (`mspm0_sdk`) | `arm-none-eabi-gcc` | `make all` |
| Rust | b01lers eCTF HAL | `cargo` + `thumbv8m.main-none-eabi` | `cargo build --release` |

Disassembly: `arm-none-eabi-objdump -d -S firmware.elf`, optionally augmented with `capstone` for richer per-instruction metadata.

## REST endpoints

```
GET    /projects                              list projects
POST   /projects                              create project from template
GET    /projects/{id}                         project details + versions
DELETE /projects/{id}                         delete (soft: move to ~/emfi-projects/.trash/)

GET    /projects/{id}/tree                    file tree
GET    /projects/{id}/file?path=...           file contents
PUT    /projects/{id}/file?path=...           upsert file contents

POST   /projects/{id}/git/commit              { message }
POST   /projects/{id}/git/tag                 { name }
GET    /projects/{id}/git/log

POST   /projects/{id}/build                   { version? } — kick a build, returns sha
GET    /projects/{id}/builds                  list build artifacts
GET    /projects/{id}/builds/{sha}            BuildArtifact
GET    /projects/{id}/builds/{sha}/firmware.elf  download
GET    /projects/{id}/builds/{sha}/disassembly   AssemblyListing

GET    /projects/{id}/targets                 list GlitchTargets
POST   /projects/{id}/targets                 add target (writes targets.json + git commit)
DELETE /projects/{id}/targets/{pc}            remove

POST   /projects/{id}/agent                   { prompt } — invoke claude CLI

GET    /templates                             list project templates
```

## WebSocket `/ws`

Topics:
- `build_log` — streaming stdout/stderr of `make` or `cargo build`
- `build_status` — `{ project_id, sha, phase: starting|compiling|linking|disassembling|done|failed }`
- `agent_output` — streaming stdout/stderr of `claude` subprocess

## Agent integration

`POST /projects/{id}/agent` body:
```json
{ "prompt": "Add a deliberate single-instruction branch to glitch", "model": "opus" }
```

Backend spawns:
```bash
cd ~/emfi-projects/{id} && claude --print "<prompt>"
```
or uses `claude` in agent mode (final flag set TBD when wiring). Streams stdout via WebSocket topic `agent_output`. After the agent exits, the working tree changes are surfaced to the frontend; user can commit / tag / build them.

## Templates

Bundled under `backend/develop/templates/`:

- **`c_ti_hal/`** — minimal MSPM0L2228 C project. Includes:
  - `Makefile` with `arm-none-eabi-gcc` invocation, linker script
  - `src/main.c` — Scaffold-style heartbeat + USER_TEST loop
  - `linker.ld` — MSPM0L2228 memory map
  - `targets.json` — empty `[]`
- **`rust_b01lers/`** — minimal Rust project against b01lers eCTF HAL:
  - `Cargo.toml` with `thumbv8m.main-none-eabi` target
  - `src/main.rs` — `#![no_std]` `#![no_main]`, b01lers HAL boot
  - `targets.json` — empty `[]`

Both templates compile out-of-the-box and produce a runnable binary that exercises the Scaffold pin protocol from the old `main.py`.

## Frontend pages

| Route | Purpose |
|---|---|
| `/` | Project list. New / open / delete. |
| `/projects/[id]` | Project editor: file tree, Monaco editor, build console, git ops. |
| `/projects/[id]/asm` | Assembly view + target picker. Renders disassembly with click-to-mark targets. |

Frontend components (Svelte):
- `MonacoEditor.svelte` — wraps the VS Code Monaco editor.
- `AssemblyView.svelte` — virtualized listing of `AssemblyInstruction[]` with click → target.
- `BuildLog.svelte` — append-only log view fed by WS topic `build_log`.
- `ProjectTree.svelte` — file tree.

## Deterministic build SHA

```
sha = sha256(
  archive of src/ at HEAD + project.toml +
  toolchain-versions.txt
)
```

`toolchain-versions.txt` is captured at build time from `arm-none-eabi-gcc --version` / `cargo --version`. This is what Control pins against.

## Out of scope (Phase 2+)

- Build caching beyond per-sha
- Multi-rig artifact sharing
- Agent loops that build → flash → measure (this could be a future "auto-glitch-finder" feature spanning all three apps)
