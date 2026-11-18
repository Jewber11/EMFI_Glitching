# View — Scaffold Audit Report

Audited against `SPEC.md`, `../ARCHITECTURE.md`, and the plan file.

## Pages (Routes)

| Route | Spec | Status | File |
|---|---|---|---|
| `/` | Mission control | **[drift]** | `src/routes/+page.svelte` — renders position/counters/log inline; spec says it should use ArmButton, StopButton, DeviceStatusCard, LogTail components |
| `/campaign` | Campaign config | [present] | `src/routes/campaign/+page.svelte` |
| `/campaign/[id]` | Live campaign view | [present] | `src/routes/campaign/[id]/+page.svelte` |
| `/runs` | Logbook browser | [present] | `src/routes/runs/+page.svelte` |
| `/heatmap` | 2D fault density | [present] | `src/routes/heatmap/+page.svelte` |
| `/assembly` | Standalone assembly viewer | [present] | `src/routes/assembly/+page.svelte` |

## Components

| Component | Spec | Status | File |
|---|---|---|---|
| `ArmButton.svelte` | Hold-to-arm (1s) | [present] | `src/lib/components/ArmButton.svelte` |
| `StopButton.svelte` | Big red, Esc/Space, calls POST `/campaigns/{id}/stop` | **[drift]** | `src/lib/components/StopButton.svelte` — uses generic `onStop` callback, not wired to API; not a permanent floating button per Safety UX |
| `Scene3D.svelte` | Three.js stage | [present] | `src/lib/components/Scene3D.svelte` |
| `Heatmap.svelte` | 2D canvas | [present] | `src/lib/components/Heatmap.svelte` |
| `LogTail.svelte` | Append-only, capped at N | [present] | `src/lib/components/LogTail.svelte` |
| `DeviceStatusCard.svelte` | Per-device status card | [present] | `src/lib/components/DeviceStatusCard.svelte` |
| `SweepConfig.svelte` | Sweep range inputs | [present] | `src/lib/components/SweepConfig.svelte` |
| `GridConfig.svelte` | Grid extent inputs | [present] | `src/lib/components/GridConfig.svelte` |

## Stores

| Store | Spec | Status | File |
|---|---|---|---|
| `arm.ts` | `{ armed, seconds_until_auto_disarm }` | [present] | `src/lib/stores/arm.ts` |
| `position.ts` | `{ x, y, z, machine_xyz }` | [present] | `src/lib/stores/position.ts` |
| `counters.ts` | from WS topic `counter` | [present] | `src/lib/stores/counters.ts` |
| `log.ts` | derived `attempt[]` (capped) | [present] | `src/lib/stores/log.ts` |
| `devices.ts` | `Map<name, DeviceStatus>` from WS topic `device_status` | **[missing]** | Not created |

## WS Connections

| Item | Spec | Status | File |
|---|---|---|---|
| `control_ws.ts` | Single shared WS to Control | **[drift]** | `src/lib/ws/control_ws.ts` — handles `position`, `arm`, `counter`, `attempt` but **missing** `device_status` and `campaign_progress` topics |
| `develop_ws.ts` | On-demand WS to Develop | [present] | `src/lib/ws/develop_ws.ts` |

## API Clients

| Function | Spec implies | Status | File |
|---|---|---|---|
| `armState()` | GET `/arm_state` | [present] | `src/lib/api/control.ts` |
| `arm()` | POST `/arm` | [present] | `src/lib/api/control.ts` |
| `disarm()` | POST `/disarm` | [present] | `src/lib/api/control.ts` |
| `moveAbs()` | POST `/motion/move_abs` | [present] | `src/lib/api/control.ts` |
| `startCampaign()` | POST `/campaigns` | [present] | `src/lib/api/control.ts` |
| `listRuns()` | GET `/runs?...` | [present] | `src/lib/api/control.ts` |
| `heatmap()` | GET `/heatmap?z=...` | [present] | `src/lib/api/control.ts` |
| `replay()` | POST `/replay/{id}` | [present] | `src/lib/api/control.ts` |
| `devices()` | GET `/devices` (mission control reads this) | **[missing]** | `src/lib/api/control.ts` |
| `getCampaign()` | GET `/campaigns/{id}` (live campaign page reads this) | **[missing]** | `src/lib/api/control.ts` |
| `stopCampaign()` | POST `/campaigns/{id}/stop` (StopButton calls this) | **[missing]** | `src/lib/api/control.ts` |
| `listProjects()` | GET `/projects` | [present] | `src/lib/api/develop.ts` |
| `getProject()` | GET `/projects/{id}` | [present] | `src/lib/api/develop.ts` |
| `listBuilds()` | GET builds | [present] | `src/lib/api/develop.ts` |
| `disassembly()` | GET disassembly listing | [present] | `src/lib/api/develop.ts` |
| `listTargets()` | GET targets | [present] | `src/lib/api/develop.ts` |

## Safety UX

| Requirement | Status |
|---|---|
| ArmButton hold 1000ms | [present] |
| Stop as top-level keyboard shortcut (Esc, Space) | [present] |
| Stop as permanent floating button | **[missing]** — StopButton exists but is not placed floating in the layout |
| Active arm state in header at all times | [present] — `+layout.svelte` shows armed/safe |
| Auto-disarm countdown in header | **[missing]** — layout only shows "ARMED"/"safe", no countdown |

## Dependencies (package.json)

| Dep | Spec implies | Status |
|---|---|---|
| three | Three.js for Scene3D | [present] |
| monaco-editor | Monaco for assembly view | [present] |
| @sveltejs/kit | SvelteKit | [present] |
| @sveltejs/adapter-static | Static build | [present] |
| openapi-typescript | Type generation | [present] |

## Config

| Item | Status | File |
|---|---|---|
| `config.ts` | [present] | `src/lib/config.ts` — CONTROL_URL + DEVELOP_URL + wsUrl helper |

---

## Summary of Findings

### [missing] — 6 items
1. `src/lib/stores/devices.ts` — store for device statuses
2. `device_status` topic in `control_ws.ts` dispatch
3. `campaign_progress` topic in `control_ws.ts` dispatch
4. `devices()` function in `src/lib/api/control.ts`
5. `getCampaign()` function in `src/lib/api/control.ts`
6. `stopCampaign()` function in `src/lib/api/control.ts`

### [drift] — 3 items
1. `+page.svelte` renders data inline instead of using spec'd components (ArmButton, StopButton, DeviceStatusCard, LogTail)
2. `+layout.svelte` missing auto-disarm countdown and floating StopButton
3. `StopButton.svelte` takes generic callback instead of wiring to `stopCampaign` API

### [extra] — none
