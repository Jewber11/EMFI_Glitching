# EMFI Research Platform — Architecture

## Why three apps

The previous codebase (`old-em-setup/glitchweb/`) conflated three concerns: hardware control, firmware development, and visualization. This rebuild splits them along the lines of *what they own*:

- **Control owns hardware.** It is a singleton — there is exactly one instance per physical rig because the USB devices can only be opened by one process. Safety state (ARM gate, rate limiter) lives here because that is where the high voltage is generated.
- **Develop owns firmware artifacts.** Projects, builds, disassembly listings, glitch-target annotations. No hardware, no safety state. Independent of Control entirely — it can run on a dev laptop if useful.
- **View owns presentation.** Stateless. Many tabs can be open at once. Talks to both Control and Develop over HTTP/WS.

A fourth shared `protocol/` folder publishes Pydantic models and OpenAPI specs as the canonical contract.

## Topology

```
┌──────────────────── Lab Computer (Linux) ────────────────────┐
│                                                               │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐       │
│  │  Control    │    │  Develop    │    │  View       │       │
│  │  :8001      │    │  :8002      │    │  :8003      │       │
│  │  FastAPI+WS │    │  FastAPI+WS │    │  SvelteKit  │       │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘       │
│         │ USB              │ filesystem      │                │
│         ▼                  ▼                 │                │
│  Shover/Shouter/           ~/emfi-projects/  │                │
│  Scaffold/XDS110           gcc / cargo /     │                │
│  └→ MSPM0L2228             objdump / openocd │                │
└──────────────────────────────────────────────┼────────────────┘
                                               │
                          Lab LAN (HTTP) ──────┘
                          (browsers, dev laptops)
```

## Campaign flow

```
View → Develop  GET  /projects                       list projects+versions
View → Develop  POST /projects/{id}/build            build firmware
                ← .elf + assembly listing + symbols
View                                                  user picks target instruction in
                                                      assembly view → compute glitch delay
View → Control  POST /campaigns                      {project_ref, sweep, grid}
Control → Develop GET /artifacts/{hash}/firmware.elf pull build artifact
Control                                              flash via XDS110 (UniFlash/dslite for
                                                     prod; OpenOCD when debugger attached)
Control                                              run scan loop, stream over WS:
                                                       - position updates
                                                       - per-attempt verdicts
                                                       - counter snapshots
View                                                  render 3D scene + heatmap + log tail
```

## Carry-forward patterns from `old-em-setup/`

These are hard-won pieces that must survive into Control unchanged in spirit:

| Pattern | Old file | Reason |
|---|---|---|
| `DeviceWorker` (single-thread executor per device) | `glitchweb/backend/app/workers.py` | pyserial concurrency safety. Two browser tabs racing on a port → corrupted writes without this. |
| `ArmGate` / `RateLimiter` / `StopFlag` | `glitchweb/backend/app/safety.py` | High-voltage pulses must be gated by explicit user intent and rate-limited to safe levels. |
| JSONL append-only logbook | `glitchweb/backend/app/logbook.py` | Research log: immutable, grep-able, replay-able. Canonical record. |
| `AppState` + `Broadcaster` | `glitchweb/backend/app/state.py` | Single source of truth pushed to all WS clients. |
| Trigger-mode selector (software / one-shot / free-run) | `glitchweb/backend/app/orchestrator.py` | Bug fix from real lab incident — ChipSHOUTER A0 free-runs uncontrollably if raw D0 → A0. |
| VID/PID-based port classification | `glitchweb/backend/app/ports.py` | Cables move; device paths change. Identify by VID/PID + serial prefix. |

## What's new vs the old setup

- **XDS110 programming** — old setup had no automated flashing path. Control gains a `/target/flash` endpoint (UniFlash/dslite subprocess) and a `/target/debug_attach` endpoint (OpenOCD subprocess for combined SW+HW attack analysis).
- **Multi-language firmware** — Develop supports C (TI ecosystem, MSPM0 SDK) **and** Rust against the b01lers eCTF HAL.
- **Assembly-level glitch targeting** — Develop builds an instruction-level listing, View shows it with click-to-pick targets, and a delay calculator translates `(instruction PC, cycles to it, scaffold offset)` into a microsecond glitch delay.
- **Agent firmware generation** — Develop shells out to `claude` CLI in the project directory for AI-assisted firmware authoring.
- **SQLite index over JSONL** — JSONL stays canonical; SQLite mirror gives fast `GROUP BY` for heatmap and `WHERE` filters for replay.
- **Extended sweep dimensions** — old scan only iterated XYZ. Campaign engine now sweeps XYZ × delay × pulse width × voltage.
- **Replay mode** — pick any historical run from the logbook, jog to that XYZ, re-fire that exact glitch.

## Tech stack

| Layer | Tool |
|---|---|
| Control backend | Python 3.11+, FastAPI, uvicorn, Pydantic v2, pyserial |
| Control adapters | `chipshover`, `chipshouter`, `donjon-scaffold` (pip), `openocd` subprocess, TI `dslite`/UniFlash subprocess |
| Control storage | JSONL canonical + SQLite index |
| Develop backend | Python 3.11+, FastAPI, GitPython or subprocess git, `pyelftools`, optional `capstone` |
| Develop frontend | SvelteKit + Vite + Monaco (served via FastAPI StaticFiles in prod) |
| Develop toolchains | `arm-none-eabi-gcc`, `arm-none-eabi-objdump`, `cargo` + `rustup target add thumbv8m.main-none-eabi` |
| Develop agent | `claude` CLI subprocess |
| View | SvelteKit + Vite + Three.js + Monaco |
| Shared contracts | Pydantic v2 (`protocol/`), OpenAPI 3.1, `openapi-typescript` |
| Comms | HTTP + WebSocket, plain text on LAN |

## Decisions explicitly made

- **Monorepo, not three repos.** One repo with `control/`, `develop/`, `view/`, `protocol/`. Cross-app refactors stay atomic; protocol is single-source-of-truth without publishing.
- **Develop has its own UI.** It is usable standalone via `http://lab-box:8002/`, in addition to View pulling its data.
- **SvelteKit for both frontends.** Less ceremony than React for dashboards; the assembly viewer + 3D + heatmap are well-supported.
- **OpenOCD for debugging; UniFlash/dslite for production flashing.** UniFlash is faster for the common "flash and run a campaign" loop; OpenOCD enables stepping through code while glitching it. Both exposed as Control endpoints.
- **Claude Code CLI for agent firmware generation in V1.** Wired via subprocess in Develop; requires `claude` installed on the lab box.
- **No cloud in V1.** Lab is air-gapped to a LAN. Architecture allows a future S3/Blob nightly backup task without redesign.
- **Phase 2 deferrals**: USB webcam overlay + click-to-jog calibration, continuous heartbeat watcher coroutine, delta-encoded WS broadcasts, cross-rig comparison, cloud archive.

## Inter-service contract

- **REST** for commands and queries (Control + Develop are both FastAPI; OpenAPI is auto-generated).
- **WebSocket** for live telemetry: Control's `/ws` streams position/attempt/counter events; Develop's `/ws` streams build logs and agent output.
- **No message broker.** YAGNI for a single rig. Revisit only if multiple rigs ever need to coordinate.
- **No auth, no TLS.** LAN-only deployment is the user requirement. All endpoints are open to anyone on the network.

## Where data lives

```
~/.local/share/emfi-control/
  sessions/
    logbook-YYYYMMDD.jsonl       # canonical JSONL (carry-forward format)
    index.sqlite                 # mirror for fast queries

~/.config/emfi-control/
  config.json                    # device discovery, safety params, ports

~/emfi-projects/
  <project-id>/
    project.toml                 # name, language, hal, version
    src/                         # firmware source
    targets.json                 # GlitchTarget annotations (PC → metadata)
    .git/                        # versions = git tags
    builds/<sha>/                # deterministic build outputs
      firmware.elf
      firmware.bin
      firmware.lst               # objdump -d
      symbols.json
```

## File map

Each app is independently buildable. See per-app docs:

- [`protocol/README.md`](./protocol/README.md) — shared models
- [`control/SPEC.md`](./control/SPEC.md) — Control API + safety contract
- [`develop/SPEC.md`](./develop/SPEC.md) — Develop API + project model
- [`view/SPEC.md`](./view/SPEC.md) — View pages + components

The original implementation in [`old-em-setup/`](./old-em-setup/) is preserved verbatim as a reference for the carry-forward modules and the bug history documented in `old-em-setup/HANDOFF.md`.
