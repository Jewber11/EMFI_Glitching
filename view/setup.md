# view/ — local setup (deployment-specific)

You are working in the View app of a 3-app EMFI research platform. View is the **unified dashboard** — pure SvelteKit static, talks to Control + Develop over HTTP + WebSocket, owns no state of its own.

## Where this runs

| | |
|---|---|
| Host | `faultierHost2` at `10.164.9.112` (Kali rolling 2025.4, amd64) |
| User | `stephen` |
| Repo | `/home/stephen/EM-Architecture/` |
| SSH alias | `ssh em-lab` |
| Node | 20.19.5, npm 11.13.0 |
| URL | `http://10.164.9.112:8003/` |
| Production build output | `view/build/` (already produced; static files only) |

## Services this app consumes

Both live on the same lab box.

| Service | URL | Provides |
|---|---|---|
| Control | `http://10.164.9.112:8001/` | hardware state, campaigns, campaign metadata, runs, heatmap/cell drill-down, arm gate, motion, shouter, flash, AD2 capture. WS `/ws`: `position`, `arm`, `counter`, `attempt`, `ad2_capture`, `device_status`, `campaign_progress`, `state`, `error` |
| Develop | `http://10.164.9.112:8002/` | firmware projects, builds, disassembly, glitch-targets. WS `/ws`: `build_log`, `build_status`, `agent_output` |

URLs are configurable at build time:

```bash
VITE_CONTROL_URL=http://10.164.9.112:8001 \
VITE_DEVELOP_URL=http://10.164.9.112:8002 \
VITE_DEVELOP_SITE_URL=http://10.164.9.112:8002/ \
npm run build
```

For local dev against the lab box, `vite.config.ts` already has proxy entries — change `target` to `http://10.164.9.112:800{1,2}` if you want hot-reload on your laptop pointing at real services.

## How you actually run this app

```bash
ssh em-lab
cd ~/EM-Architecture/view

bash start.sh            # ./start.sh — production preview on 0.0.0.0:8003
                         # OR
npm run dev -- --port 8003 --host 0.0.0.0   # hot reload
npm run build            # static build → ./build/
npm run preview -- --port 8003 --host 0.0.0.0  # serve the static build
```

`start.sh` will produce a build if `./build/` is missing, then `vite preview` it.

Verify:
```
curl -I http://10.164.9.112:8003/        # HTTP 200, index.html
```

## State this app needs to receive correctly

All four stores hydrate from Control's WS `/ws`:

| Store | WS topic | Shape |
|---|---|---|
| `arm.ts` | `arm` | `{ armed, seconds_until_auto_disarm }` |
| `position.ts` | `position` | `{ x, y, z, machine_x?, machine_y?, machine_z? }` |
| `counters.ts` | `counter` | `{ attempts, glitches, hangs, crashes, nothings, campaigns }` |
| `log.ts` | `attempt` (append) | cap at 200 latest `AttemptResult` |
| `devices.ts` | `device_status` | `Map<name, DeviceStatus>` |

If you change envelope shapes in `src/lib/ws/control_ws.ts`, post in `agentConversation.md` so the Control session keeps in sync.

## Hardware *that exists right now* (informational; you don't talk to it)

| Device | Path | Identity |
|---|---|---|
| ChipShover | `/dev/ttyACM0` (Marlin) | position roughly `(0, 11, 216.5)` after homing |
| ChipSHOUTER | `/dev/ttyUSB1` | NewAE, id `5LY0MB:2.0.3`, disarmed |
| Scaffold | `/dev/ttyUSB0` | Ledger, fw 0.9 |
| XDS110 | `/dev/ttyACM1`+`/dev/ttyACM2` | TI debug probe |
| AD2 | USB WaveForms/libdwf | Dashboard scope capture: Scope CH1 pulse monitor, DIO0 trigger/ref, DIO1 ledger clock |

You'll mostly care about these for what the user *sees* — make sure DeviceStatusCard renders every listed device sensibly even when one is unavailable.

The scope panel configures the AD2 for the current 20:1 ChipSHOUTER monitor
probe, auto-starts `/devices/ad2/start_stream`, and renders live samples when
Control emits `ad2_capture`. If the AD2 or WaveForms runtime is missing, it
keeps the synthetic timing trace visible and reports AD2 as waiting.
Use the `TRIG` button for a high-speed CH1 triggered capture; it stops the live
stream, waits for a pulse-monitor edge, and renders the resulting AD2 capture.

Calibration can save the bolted-down board as the default fixture after homing.
The die map is defined by a first corner plus an opposite corner; small maps and
negative/backside directions are warnings, not blockers. Campaigns load that
saved grid and can apply the machine-space origin after ChipShover homes, so the
chip remains at logical `(0, 0)` without hand-jogging.

The Husky crowbar path is scaffolded in Control but not live hardware control
yet. View should not present dual-target/Husky campaigns as operational until
Control has real Husky connect/configure/pulse behavior and per-slot flashed
provenance.

## Safety UX — non-negotiable

Documented in `SPEC.md` § Safety UX, summarized here:

1. **ArmButton requires hold-to-arm**: 1000 ms default (read from Control's `/arm_state.auto_disarm_seconds` for the disarm window).
2. **StopButton is permanent**: floating, always reachable. Listens for **Esc** and **Space** globally.
3. **Arm indicator is always visible in the header.** Red when armed, gray when safe. Auto-disarm countdown ticks down beside it.
4. **No silent failures.** If a Control call returns an error, surface it as a toast — don't swallow.

The user can hurt themselves and the hardware with this UI. Don't move these safeguards behind any debug-mode toggle.

## Typed clients

Once Control and Develop emit OpenAPI schemas (regen target in `protocol/openapi/`), generate types:

```bash
npx openapi-typescript ../protocol/openapi/control.yaml -o src/lib/api/control.types.ts
npx openapi-typescript ../protocol/openapi/develop.yaml -o src/lib/api/develop.types.ts
```

Don't hand-maintain types in parallel — drift will bite you within a week.

## Cross-app communication

Append-only `agentConversation.md` at the repo root. Use it when:
- You add a new page that needs a new endpoint or WS topic from Control/Develop
- You change the shape you expect from a WS event (so the Python side can update emitter accordingly)
- You discover that an endpoint returns a different shape than `SPEC.md` says

## Out of scope (Phase 2)

USB camera overlay, click-to-jog calibration, cross-rig comparison, multi-user state. File ideas, don't implement.

## When in doubt

- `SPEC.md` — authoritative pages + components + stores contract
- `AUDIT.md` — initial scaffold audit findings
- `../ARCHITECTURE.md` — system rationale
- `../agentsNotes.md` — repo-wide notes for AI sessions
- Drop a note in `../agentConversation.md` if you need something from Control or Develop
