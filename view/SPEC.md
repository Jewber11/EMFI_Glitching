# View — Spec

## Purpose

Single unified UI for the lab rig. Drives campaigns through Control, picks firmware via Develop, visualizes everything that happens.

Stateless against hardware. All shared state lives on Control (singleton) and is hydrated via Control's WS stream.

## Pages

| Route | Purpose | Reads from |
|---|---|---|
| `/` | **Mission control.** ArmButton, current position, counters, device statuses, live log tail. The "I'm at the rig" landing page. | Control: `/arm_state`, `/devices`, `/ws` (position, arm, counter, attempt) |
| `/campaign` | **Configure** a new campaign: pick project + version (Develop), pick assembly target (Develop), set sweep ranges + grid, hit Start. | Develop: `/projects`, `/projects/{id}/builds/{sha}/disassembly`; Control: `/campaigns` |
| `/campaign/[id]` | **Live campaign view.** 3D scene with current position, progress bar, last N attempts, current sweep params. | Control: `/campaigns/{id}`, `/ws` (campaign_progress, attempt, position) |
| `/runs` | **Logbook browser.** Filter/sort attempts by campaign/outcome/since. Click a row → "Replay" button → POST `/replay/{id}`. | Control: `/runs?...` |
| `/heatmap` | **2D fault density.** Canvas grid colored by attempt outcomes at each XY. Z slider switches plane. | Control: `/heatmap?z=...` |
| `/assembly` | **Standalone assembly viewer** for picking targets without going through `/campaign`. Mirrors Develop's `/projects/{id}/asm`. | Develop: `/projects`, `/projects/{id}/builds/{sha}/disassembly`, `/projects/{id}/targets` |

## Components

| Component | Notes |
|---|---|
| `ArmButton.svelte` | Hold-to-arm (1 s by default). Touch + keyboard ARMs and disarms. Disabled state shows ETA to auto-disarm. |
| `StopButton.svelte` | Big red. Listens for Esc / Space globally as panic-stop. Calls `POST /campaigns/{id}/stop`. |
| `Scene3D.svelte` | Three.js. Renders the X/Y/Z gantry, the DUT, and the current shover position. Click on the plane jogs there (calls `/motion/move_abs`). |
| `Heatmap.svelte` | 2D canvas. Inputs: `[{x, y, count}]`, color scale, opacity. Z-slider in parent. |
| `LogTail.svelte` | Append-only attempt list, fed by WS topic `attempt`. Capped at last N (e.g. 200). |
| `DeviceStatusCard.svelte` | One per device. Available / connected / port / last_error / busy. |
| `SweepConfig.svelte` | Inputs for delay/voltage/pulse-width ranges. Validates via emfi_protocol shape. |
| `GridConfig.svelte` | XYZ extents + step sizes. "Use current position as origin" button. |

## Stores

- `arm.ts` — `{ armed, seconds_until_auto_disarm }` from Control WS topic `arm`.
- `position.ts` — `{ x, y, z, machine_xyz }` from Control WS topic `position`.
- `counters.ts` — from Control WS topic `counter`.
- `log.ts` — derived `attempt[]` (capped) from Control WS topic `attempt`.
- `devices.ts` — `Map<name, DeviceStatus>` from Control WS topic `device_status`.

All stores are populated by a single shared WS connection to Control (managed in `src/lib/ws/control_ws.ts`).

## API clients

`src/lib/api/control.ts` and `src/lib/api/develop.ts` wrap `fetch()` with type-safe helpers generated from the OpenAPI specs in `protocol/openapi/`.

Generation command (run after either backend's API changes):

```bash
npx openapi-typescript ../protocol/openapi/control.yaml -o src/lib/api/control.types.ts
npx openapi-typescript ../protocol/openapi/develop.yaml -o src/lib/api/develop.types.ts
```

## Safety UX

- ArmButton is required-hold for 1000 ms by default (configurable via Control's `/arm_state`).
- Stop is a top-level keyboard shortcut (Esc, Space) AND a permanent floating button.
- The active arm state is shown in the header at all times — never let the user lose track of whether the rig is hot.
- Auto-disarm countdown ticks down in the header.

## Out of scope (Phase 2+)

- Camera overlay + click-to-jog calibration (Phase 2 across Control + View).
- Cross-rig comparison view (multi-rig deployments).
- Per-user state / saved layouts (no auth in V1).
