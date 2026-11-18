# Agent Notes — View App

## What this app is

Pure SvelteKit static app (port 8003). No backend. Talks to Control (:8001) and Develop (:8002) over HTTP + WebSocket. It's the unified dashboard for the EMFI research rig — campaign control, live telemetry, heatmaps, assembly viewing, logbook.

## Current state (fully implemented)

All pages, components, stores, and API clients are implemented with working UI matching the old glitchweb frontend's dark theme and feature set. The app type-checks clean (0 errors) and builds to static output.

### Dark theme

CSS custom properties in `src/app.css` match the old glitchweb palette:
- `--bg: #0e0f12`, `--panel: #161922`, `--panel-2: #1e2230`
- `--accent: #00d18f` (teal), `--warn: #f9a825`, `--err: #ff5252`, `--ok: #00c853`
- System UI font stack, monospace for data displays

### What was built

**Layout & topbar** (`+layout.svelte`):
- Dark header with nav links, device status lights, arm button + arm state indicator with countdown, stop button
- Active page highlighting in nav
- Toast notification system (bottom-right, auto-dismiss)

**Mission control** (`/`, three-column layout like old glitchweb):
- Left sidebar: position readout, jog pad (XY + Z), campaign progress bar
- Center: full Three.js 3D scene with probe, grid, axes, attempt trail, scan box, orbit controls, double-click-to-jog
- Right sidebar: counter panel (attempts/faults/hangs/crashes/nothings/campaigns/success%), logbook table with filtering and click-to-highlight

**Campaign config** (`/campaign`):
- Project picker (from Develop), version selector
- Shouter config: trigger mode, voltage, pulse width, verdict timeout, mute, auto-arm
- Grid config: origin/top-right with "use current position" buttons, step size, Z range
- Sweep config: toggleable delay/pulse/voltage ranges with start/stop/step, attempts per point
- Start button → POST /campaigns → redirect to live view

**Live campaign** (`/campaign/[id]`):
- Progress bar from campaign_progress WS topic
- Scene3D + LogTail side by side
- Campaign config dump, stop button

**Runs browser** (`/runs`):
- Outcome and campaign filters
- Full table: time, outcome, XYZ, delay, width, voltage, elapsed
- Click row for details, replay button per row

**Heatmap** (`/heatmap`):
- Z slider, campaign filter, refresh
- Canvas rendering with blue→green→yellow→red color scale
- Hover tooltip showing (x, y, count)
- Axis labels

**Assembly viewer** (`/assembly`):
- Project picker, build SHA input
- Disassembly table: PC, bytes, mnemonic+operands, function, source location
- Syntax coloring (teal mnemonics, amber functions)
- Filter by mnemonic/function/PC
- Target-annotated rows highlighted in accent

### Components

| Component | Status |
|---|---|
| `ArmButton.svelte` | Hold-to-arm with progress bar fill animation, amber/red states |
| `StopButton.svelte` | Red, Esc shortcut (scoped: skips input/textarea/select focus) |
| `Scene3D.svelte` | Full Three.js: probe cone, XY grid, axes, outcome point trails (4 colors), scan box wireframe, highlight ring, orbit controls, double-click-to-jog via raycasting |
| `Heatmap.svelte` | Canvas rendering with color scale, hover tooltip, axis labels |
| `LogTail.svelte` | Table with sticky header, outcome filter dropdown, outcome coloring, click-to-select, auto-scroll |
| `DeviceStatusCard.svelte` | Compact inline badge: status dot (green/red/gray), name, port, busy indicator |
| `SweepConfig.svelte` | Toggleable range inputs for delay/pulse/voltage, attempts per point |
| `GridConfig.svelte` | Origin/top-right with "use current position", step size, Z range, area display |
| `Toast.svelte` | Fixed bottom-right, level-colored left border, auto-dismiss, click to close |
| `JogPad.svelte` | Plus-shaped XY grid + Z column, step size input, home button |
| `CounterPanel.svelte` | Styled counter rows with outcome colors, success percentage |
| `ProgressBar.svelte` | Animated fill bar with value/max label |

### Stores

| Store | Purpose |
|---|---|
| `arm.ts` | Arm state from WS |
| `position.ts` | XYZ position from WS |
| `counters.ts` | Attempt outcome counters from WS |
| `devices.ts` | Map<name, DeviceStatus> from WS |
| `log.ts` | AttemptEntry[] (capped at 200) from WS |
| `campaign.ts` | Active campaign progress from WS |
| `toast.ts` | Toast notification queue |

### API clients

**control.ts** (19 functions): armState, arm, disarm, moveAbs, moveRel, home, startCampaign, listCampaigns, getCampaign, stopCampaign, listRuns, heatmap, replay, devices, connectDevice, shouterConfig, shouterPulse, shouterArm, shouterDisarm

**develop.ts** (5 functions): listProjects, getProject, listBuilds, disassembly, listTargets

### WS

**control_ws.ts**: auto-reconnect with exponential backoff (500ms → 5s cap), dispatches 7 topics (position, arm, counter, attempt, device_status, campaign_progress, error), toast on connect/disconnect/error

**develop_ws.ts**: on-demand connection with connect/disconnect/error logging

## File map

```
view/
  start.sh                              # startup script (dev or preview mode)
  logs/                                 # server logs (gitignored, created by start.sh)
  package.json
  svelte.config.js                      # adapter-static, fallback to index.html
  vite.config.ts                        # proxy /control→:8001, /develop→:8002
  tsconfig.json
  SPEC.md                               # API contract & requirements
  AUDIT.md                              # scaffold audit report
  src/
    app.html
    app.css                             # dark theme (matches old glitchweb palette)
    routes/
      +layout.svelte                    # topbar, device lights, arm indicator, nav, toast
      +page.svelte                      # mission control (3-column: jog|scene|counters+log)
      campaign/+page.svelte             # campaign config form (project, shouter, grid, sweep)
      campaign/[id]/+page.svelte        # live campaign (progress, scene, log, config)
      runs/+page.svelte                 # logbook browser (filter, table, replay, detail)
      heatmap/+page.svelte              # heatmap (Z slider, canvas, tooltip)
      assembly/+page.svelte             # assembly viewer (project picker, disassembly table)
    lib/
      config.ts                         # CONTROL_URL, DEVELOP_URL, wsUrl()
      logger.ts                         # structured logging: createLogger(category)
      api/
        control.ts                      # 19 functions wrapping Control REST endpoints
        develop.ts                      # 5 functions wrapping Develop REST endpoints
      ws/
        control_ws.ts                   # always-on WS with auto-reconnect, 7 topics
        develop_ws.ts                   # on-demand WS for build/agent streaming
      stores/
        arm.ts                          # arm state
        position.ts                     # XYZ position
        counters.ts                     # outcome counters
        devices.ts                      # Map<name, DeviceStatus>
        log.ts                          # AttemptEntry[] (capped at 200)
        campaign.ts                     # active campaign progress
        toast.ts                        # toast notification queue
      components/
        ArmButton.svelte                # hold-to-arm with progress fill
        StopButton.svelte               # red stop, Esc shortcut
        Scene3D.svelte                  # Three.js (probe, grid, trails, click-to-jog)
        Heatmap.svelte                  # 2D canvas with color scale + tooltip
        LogTail.svelte                  # table with filter, outcome colors, click-select
        DeviceStatusCard.svelte         # inline device badge with status dot
        SweepConfig.svelte              # toggleable sweep range inputs
        GridConfig.svelte               # grid inputs with "use position" buttons
        Toast.svelte                    # notification toasts
        JogPad.svelte                   # XYZ jog buttons + home
        CounterPanel.svelte             # styled counter display
        ProgressBar.svelte              # animated progress bar
```

## How to run

```bash
./start.sh dev          # dev with hot reload on :8003
./start.sh preview      # production build + preview on :8003
./start.sh dev 3000     # custom port
```

## What's needed from Control and Develop

The View UI is complete and will render its shell regardless of backend availability. When the backends come online, these endpoints need to work:

**Control (:8001)**:
- `GET /arm_state`, `POST /arm`, `POST /disarm`
- `GET /devices`, `POST /devices/{id}/connect`
- `POST /motion/move_abs`, `POST /motion/move_rel`, `POST /motion/home`
- `POST /shouter/config`, `POST /shouter/pulse`, `POST /shouter/arm`, `POST /shouter/disarm`
- `POST /campaigns`, `GET /campaigns`, `GET /campaigns/{id}`, `POST /campaigns/{id}/stop`
- `GET /runs?outcome=&campaign=`, `GET /heatmap?z=&campaign=`, `POST /replay/{id}`
- `WS /ws` — topics: position, arm, counter, attempt, device_status, campaign_progress, error

**Develop (:8002)**:
- `GET /projects`, `GET /projects/{id}`
- `GET /projects/{id}/builds`
- `GET /projects/{id}/builds/{sha}/disassembly`
- `GET /projects/{id}/targets`
