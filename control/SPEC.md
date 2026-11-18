# Control — Spec

## Purpose

Single owner of all physical hardware on the lab rig. Exposes a REST + WebSocket API consumed by View (and optionally Develop, when Control needs to pull build artifacts).

## Invariants

1. **One process per rig.** Serial devices have exclusive open semantics.
2. **All hardware calls are serialized per device** through a `DeviceWorker` (single-thread executor). No exception.
3. **No pulse fires unless `ArmGate.require_armed()` succeeds.** This includes every code path in every router, the orchestrator, and any future feature.
4. **All pulse-emitting paths acquire a `RateLimiter` token.** Default 10/sec.
5. **The JSONL logbook is canonical.** The SQLite index is a derivable mirror, never the source of truth.
6. **State mutations broadcast.** Every change to `AppState` is followed by a `Broadcaster.broadcast()` call.

## Modules

### `safety.py` (seed)
`ArmGate` (hold-to-arm + auto-disarm timer), `RateLimiter` (sliding window), `StopFlag` (cooperative stop). Raise `Disarmed` / `RateLimited`. Carried forward from `old-em-setup/glitchweb/backend/app/safety.py`.

### `workers.py` (seed)
`DeviceWorker` wraps a `ThreadPoolExecutor(max_workers=1)` per device. `WorkerRegistry` holds one per device name. Carried forward from `old-em-setup/glitchweb/backend/app/workers.py`. Future split: separate read-queue from write-queue (status polls compete with writes today).

### `state.py` (seed)
`AppState` is the single in-memory snapshot: device statuses, position, counters, scan progress, arm state. `Broadcaster` distributes WS events with drop-oldest backpressure. Carry-forward from `old-em-setup/glitchweb/backend/app/state.py`.

### `logbook.py` (seed + new)
JSONL append-only writer carried from old code. **New**: a SQLite mirror updated on every append for the columns required by heatmap and replay queries.

### `orchestrator.py` (seed + extended)
`perform_attempt()` + `run_scan()` from old code. **Extended** with sweep dimensions (delay_us × pulse_width_ns × voltage_v) on top of the XYZ grid. Adds `replay(run_id)` that rehydrates an `AttemptResult` and re-executes the exact attempt.

### `ports.py` (seed)
VID/PID + manufacturer/serial-prefix matching. Carry-forward from `old-em-setup/glitchweb/backend/app/ports.py`.

### `config.py` (new)
JSON config under `~/.config/emfi-control/config.json` with hot reload. Schema mirrors `old-em-setup/glitchweb/backend/app/config.py` shape; auto-created on first start.

### `adapters/`
- `base.py` — common interface (`connect`, `disconnect`, `status`)
- `chipshover.py` — wraps `chipshover` pip package; XY logical↔machine coordinate transform
- `chipshouter.py` — wraps `chipshouter` pip package; idempotent arm/disarm; captures `faults_latched` (decoded names + raw bitmask) into `last_fault` before clearing; `set_pulse_width(ns)` sets the **EMFI HV pulse width** (the parameter the campaign sweep's `pulse_width_ns` controls) and reads it back
- `scaffold.py` — wraps `donjon-scaffold`; D0/D1/D2/D3 pin map, trigger-mode selector. In hardware trigger modes, `pgen0` provides only the **A0 trigger pulse**: its width is a fixed ~200 ns constant (set once at campaign start, not swept) and its delay is the per-attempt glitch delay
- `xds110.py` — subprocess wrappers:
  - `flash(elf_path)` — invokes TI `dslite` or `uniflash` CLI; fast for the "build → flash → campaign" loop
  - `attach_debugger(elf_path)` — spawns OpenOCD on configured gdb/telnet ports for SW+HW combined attack analysis

## REST endpoints

```
GET    /devices                    list discovered serial devices
GET    /devices/chipshouter/faults last latched + current ChipSHOUTER faults
POST   /devices/{name}/connect     open serial port
POST   /devices/{name}/disconnect

GET    /config                     axes + ports + safety config (read-only)

POST   /motion/move_abs            { x, y, z } logical
POST   /motion/move_rel            { axis, distance }
POST   /motion/home
POST   /motion/set_origin
POST   /motion/set_top_right       { x, y }

POST   /shouter/arm
POST   /shouter/disarm
POST   /shouter/pulse              { voltage, pulse_width_ns, repeat }
POST   /shouter/config             { voltage, pulse_width_ns, mute, ... }

POST   /target/flash               { build_sha, elf_url }
POST   /target/reset
POST   /target/debug_attach        { build_sha, elf_url, gdb_port }

POST   /campaigns                  start a campaign (Campaign model)
GET    /campaigns                  list campaigns
GET    /campaigns/{id}             status + summary
POST   /campaigns/{id}/stop

GET    /runs?campaign=...&since=...&outcome=...&limit=...
GET    /runs/{id}
GET    /heatmap?campaign=...&z=...&outcome=...   per-cell outcome counts
POST   /replay/{run_id}            re-execute that exact attempt

POST   /arm
POST   /disarm
GET    /arm_state
```

All responses use Pydantic models from `emfi_protocol`. Error responses use FastAPI's default `{ "detail": "..." }`.

`GET /heatmap` groups attempts by `(x, y)` and returns per-outcome counts so View can color-code each cell without re-querying:

```
[ { "x": 1.0, "y": 2.0,
    "counts": { "glitch": 2, "hang": 5, "crash": 0, "nothing": 8 } }, ... ]
```

`outcome` filters to a single bucket only when explicitly set; omit it (the default) to include every outcome — so the heatmap is non-empty before the first glitch lands. `z` narrows to one Z plane.

## Axis configuration

Motion coordinates have two frames: **user logical** (what the API and the
`position` WS topic report, and what the +X/+Y/+Z jog buttons mean) and
**machine** (raw gantry G-code coordinates). `set_origin` records the
current machine position as logical `(0,0,0)`; logical coordinates are
offsets from it. On top of that offset, the `axes` section of
`~/.config/emfi-control/config.json` corrects for a gantry mounted
differently from the conventional rig:

| Flag | Effect | Set it when… |
|---|---|---|
| `invert_x` | User +X → machine −X | Pressing +X jogs the stage the wrong way along X |
| `invert_y` | User +Y → machine −Y | Pressing +Y jogs the stage the wrong way along Y |
| `invert_z` | User +Z → machine −Z | +Z moves toward the bed instead of away |
| `swap_xy` | User X drives machine Y and vice versa | The stage is mounted rotated 90° (X/Y transposed) |

**Conventional setup** (all flags `false`): origin = bottom-left of the
viewable DUT, +X = right, +Y = up, +Z = away from the bed. Rigs that don't
match should set the flags above.

Transform order (user → machine): invert the user axes first, then map to
machine axes via the optional swap; reads apply the exact inverse. Because
the inversion is applied before `position` is broadcast, the user never sees
negative coordinates unless they intentionally jog into the negative region
— e.g. a gantry whose physical top-right is machine `(−10, −10)` reports
logical `(+10, +10)`, so the calibration wizard's `top_right` stays positive
and the campaign grid math (`top_right − origin`) doesn't collapse.

Changes take effect on Control restart (the config is read once at adapter
connect). `GET /config` returns the live `axes` / `ports` / `safety`
sections for display; there is no edit endpoint yet — edit the JSON file.

## WebSocket `/ws`

Server → client envelope: `emfi_protocol.WsEvent`.

Topics:
- `position` — `{ x, y, z, machine_x, machine_y, machine_z }`
- `arm` — `{ armed, seconds_until_auto_disarm }`
- `counter` — Counters snapshot
- `attempt` — `AttemptResult` (one per attempt completed). Hardware-trigger campaigns also set `shouter_pulse_width_ns_actual` (the HV pulse width the ChipSHOUTER acknowledged, vs the commanded `shouter_pulse_width_ns`).
- `device_status` — per-device `DeviceStatus`. For `chipshouter`, includes `fault_names: list[str] | null` (decoded names of the most recently latched faults).
- `campaign_progress` — `{ campaign_id, phase, completed_attempts, total_attempts, current_xyz, current_sweep }`. `phase` is one of `started | running | completed | stopped | failed` (with an optional `reason` on `failed`). Field names mirror `emfi_protocol.CampaignStatus`. `current_xyz` is `[x, y, z]` while running, `null` otherwise.
- `state` — full `AppState.snapshot()` on connect
- `error` — `{ detail, campaign_id? }`

Client → server actions (kept minimal; prefer REST for commands):
- `{ id, action: "subscribe", topics: [...] }` — optional topic filter
- `{ id, action: "ping" }`

## Storage layout

```
~/.local/share/emfi-control/
  sessions/
    logbook-YYYYMMDD.jsonl
    index.sqlite                  # mirror; schema below

~/.config/emfi-control/
  config.json
```

### SQLite schema (mirror)

```sql
CREATE TABLE runs (
  id TEXT PRIMARY KEY,
  session TEXT NOT NULL,
  ts TEXT NOT NULL,
  campaign_id TEXT,
  x REAL, y REAL, z REAL,
  delay_us REAL, pulse_width_ns REAL, voltage_v INTEGER,
  outcome TEXT NOT NULL,
  build_sha TEXT,
  target_pc INTEGER
);
CREATE INDEX idx_runs_campaign ON runs(campaign_id);
CREATE INDEX idx_runs_outcome ON runs(outcome);
CREATE INDEX idx_runs_xy ON runs(x, y);
```

Mirror is updated on every `logbook.append()`. Full rebuild from JSONL is supported via `python -m control.tools.reindex`.

## Carry-forward bugs to fix

Documented in `old-em-setup/HANDOFF.md`. Highest priority during build-out:

- `Scaffold.bus.ser.close()` pokes internal attribute → use scaffold's public close.
- `chipshouter.wait_for_arm()` infinite block on HV failure → wrap with timeout + abort.
- Status polls share the worker queue with writes → split reader/writer queues per device.
- `sys.path` injection for adapters → replaced by this package's `adapters/` module.

## Testing

Pure-Python modules have unit tests with no hardware required:
- `tests/test_safety.py` — ArmGate states, auto-disarm timing, RateLimiter window
- `tests/test_workers.py` — single-threaded serialization, future propagation
- `tests/test_state.py` — counter math, snapshot stability
- `tests/test_logbook.py` — JSONL roundtrip, since/outcome filtering, SQLite index parity
- `tests/test_orchestrator.py` — fake adapters; exercise classification + grid sweep math

Hardware-touching tests are marked `@pytest.mark.hw` and skipped by default.
