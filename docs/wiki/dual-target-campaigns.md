# Dual-target campaigns

This page sketches the next campaign model for experiments where the DUT slot is
attacked with EMFI and the Platform slot is attacked with a voltage crowbar. It
is intentionally practical: the first implementation should extend the current
single-rig campaign loop without building a generic workflow engine.

As of 2026-06-01, the current plan and implementation status is:

- DUT slot: MSPM0L2228 running the primary target firmware, attacked by
  ChipSHOUTER EMFI through the ChipShover/Scaffold trigger path.
- Platform slot: MSPM0L2228 running the coordinated platform firmware, attacked
  by a ChipWhisperer Husky crowbar path.
- Public access: `emfi.ics.red` behind Cloudflare Access plus EMFI bearer-token
  auth for automation clients.
- Implemented now: protocol models for dual-target slots/timing/sweeps/budgets,
  and a Control Husky adapter/API scaffold that reports unavailable or stub
  status safely.
- Not implemented yet: per-slot flashed provenance, real Husky hardware
  control, synchronized EMFI + Husky orchestration, and View dual-target UI.

## Goals

- Represent DUT and Platform as separate target slots, not as comments on a
  single campaign.
- Represent EMFI and crowbar pulses as synchronized actions in the same attempt.
- Keep the existing XYZ grid and EMFI sweep usable for DUT-only campaigns.
- Let preflight reject unsafe or underspecified dual-target campaigns before any
  hardware moves, arms, flashes, or pulses.
- Preserve enough per-attempt timing and verdict data to compare EMFI-only,
  voltage-only, and combined attacks later.

## Rig model

Use stable slot names in the protocol and UI:

| Slot | Meaning | Initial hardware |
|---|---|---|
| `dut` | Device under test, physically in the DUT slot on the ledger board | MSPM0L2228, XDS110 flash/debug, Scaffold DUT power |
| `platform` | Companion/platform device in the Platform slot | MSPM0L2228, XDS110 or shared debug path, Scaffold Platform power |

Use stable glitcher names:

| Glitcher | Mechanism | Timing owner |
|---|---|---|
| `chipshouter` | EMFI pulse, positioned by ChipShover over the DUT | Scaffold pgen / ChipSHOUTER trigger |
| `husky` | ChipWhisperer Husky crowbar pulse on the Platform rail | Husky trigger/crowbar module |

The first backend implementation can hard-code this two-slot rig in Control
configuration. Do not require dynamic multi-rig discovery before the basic
campaign path works.

## Protocol shape

Keep the existing `Campaign.grid` and `Campaign.sweep` fields for legacy
DUT-only EMFI campaigns. Add optional dual-target fields that become required
when `mode == "dual_target"`:

```json
{
  "mode": "dual_target",
  "name": "ectf-dual-glitch-smoke",
  "project_id": "ectf-dut",
  "build_sha": "dut-build-sha",
  "target_pc": 134222912,
  "slots": {
    "dut": {
      "project_id": "ectf-dut",
      "build_sha": "dut-build-sha",
      "power_rail": "scaffold.dut",
      "programmer": "xds110:dut",
      "uart": "uart0",
      "glitcher": "chipshouter"
    },
    "platform": {
      "project_id": "ectf-platform",
      "build_sha": "platform-build-sha",
      "power_rail": "scaffold.platform",
      "programmer": "xds110:platform",
      "uart": "uart1",
      "glitcher": "husky"
    }
  },
  "timing": {
    "reference": {
      "source": "dut.gpio.d0",
      "edge": "rising",
      "description": "Firmware trigger edge observed by Scaffold/Husky"
    },
    "timeline": [
      {
        "at_us": 0.0,
        "target": "dut",
        "device": "scaffold",
        "action": "wait_for_trigger",
        "source": "dut.gpio.d0"
      },
      {
        "at_us": 1.2,
        "target": "dut",
        "device": "chipshouter",
        "action": "emfi_pulse",
        "delay_sweep": "emfi_delay_us",
        "width_sweep": "emfi_width_ns",
        "voltage_sweep": "emfi_voltage_v"
      },
      {
        "at_us": 1.6,
        "target": "platform",
        "device": "husky",
        "action": "crowbar_pulse",
        "delay_sweep": "crowbar_delay_us",
        "width_sweep": "crowbar_width_ns"
      }
    ]
  },
  "sweeps": {
    "emfi_delay_us": { "start": 0.8, "stop": 2.0, "step": 0.1 },
    "emfi_width_ns": { "start": 80, "stop": 80, "step": 1 },
    "emfi_voltage_v": { "start": 250, "stop": 250, "step": 1 },
    "crowbar_delay_us": { "start": 1.0, "stop": 2.5, "step": 0.1 },
    "crowbar_width_ns": { "start": 40, "stop": 120, "step": 20 }
  },
  "budgets": {
    "max_attempts": 1000,
    "max_runtime_s": 1800,
    "stop_on_first_crash": true,
    "max_emfi_voltage_v": 500,
    "max_crowbar_width_ns": 500
  }
}
```

Field notes for the protocol fields:

- `mode`: default `single_target` for current campaigns.
- `slots`: per-slot firmware, power, UART, programmer, and glitcher mapping.
- `timing.reference`: the signal all relative timings are measured from.
- `timing.timeline`: ordered per-attempt actions. The first implementation only
  needs `wait_for_trigger`, `emfi_pulse`, and `crowbar_pulse`.
- `sweeps`: named sweep ranges so timeline actions can bind to a sweep by name.
- `budgets`: required for unattended or agent-launched campaigns.

Avoid a fully general DAG or script language for now. A flat timeline is enough
for coordinated DUT EMFI plus Platform crowbar tests and is easy to display,
preflight, audit, and replay.

## Campaign lifecycle

1. Build or select pinned DUT and Platform firmware artifacts in Develop.
2. Flash both slots through Control target routes.
3. Record flashed provenance for both slots:
   `slot`, `project_id`, `build_sha`, `artifact`, `programmer`, and timestamp.
4. Create the dual-target campaign body with explicit slot mappings and timing.
5. Call `POST /api/control/campaigns/preflight`; do not move or pulse hardware
   during preflight.
6. Arm only after preflight passes and the caller has the right scope.
7. Start the campaign with `POST /api/control/campaigns`.
8. For each attempt:
   - move to the next DUT EMFI grid position;
   - program Scaffold pgen / ChipSHOUTER timing;
   - program Husky crowbar timing;
   - power-cycle or reset the requested slots if the campaign asks for it;
   - wait for the reference trigger;
   - fire the timeline actions;
   - collect DUT and Platform UART/GPIO verdicts;
   - append one attempt row with all commanded and observed timing.
9. Stop on explicit STOP, budget exhaustion, first-crash policy, hardware fault,
   missing heartbeat, or operator disarm.

## Preflight requirements

Preflight should return a structured pass/fail result with warnings. It should
not modify hardware state.

Required checks:

- Cloudflare Access plus EMFI bearer-token auth is active for public automation.
- Caller has `campaign:preflight`; starting later requires `campaign:start`.
- Both `dut` and `platform` slots declare `project_id` and `build_sha`.
- Last flashed provenance for each slot matches the requested build.
- Scaffold DUT and Platform power routes are known and controllable.
- ChipShover, ChipSHOUTER, Scaffold, Husky, and required programmers are
  available when the campaign uses them.
- ChipSHOUTER voltage, EMFI pulse width, crowbar pulse width, and attempt count
  are inside configured safety limits.
- Timeline actions are ordered, non-negative, and use known devices.
- Sweep names referenced by timeline actions exist.
- Total attempt count and runtime estimate fit the submitted budget.
- Trigger source is available to both timing paths or the configured fanout is
  documented.
- ARM state policy is explicit: manual arm, agent arm allowed, or reject.

Current preflight only fully covers the single-target path plus submitted
`automation_policy` caps (`max_attempts`, `max_runtime_seconds`, `max_voltage`,
and `allowed_trigger_modes`). Dual-target slot/timeline validation currently
happens in the protocol model; hardware readiness, per-slot provenance, rail
policy, and Husky availability checks still need to be added to preflight.

Warnings that should not necessarily block:

- Platform UART verdict is disabled or still marked `TBD`.
- PC target is a range but no end-delay estimate is available.
- Husky timing is software-triggered instead of hardware-triggered.
- XDS110 for one slot is disconnected after flash but not required for the run.

## API and auth considerations

AI agents should use the narrow automation flow documented in
`docs/automation.md`; they should not drive raw motion, pulse, or power routes
directly for normal campaigns.

Recommended scopes:

| Client | Scopes |
|---|---|
| Observer | `control:read`, `develop:read` |
| Builder/flasher | `develop:read`, `develop:build`, `target:flash` |
| Campaign agent | `control:read`, `develop:read`, `campaign:preflight`, `campaign:start`, `campaign:stop` |
| Human operator | Add `devices:write`, `motion:write`, `shouter:write`, `safety:arm` as needed |

Potential later scopes if dual-target control gets more granular:

- `target:flash:dut`
- `target:flash:platform`
- `campaign:start:dual_target`
- `husky:write`

The audit log should include the authenticated principal for dual-target
preflight, flash, arm, start, stop, power, and replay actions.

## Data and logging

Extend `AttemptResult` or add a versioned attempt payload so each row captures
both mechanisms without losing legacy heatmap fields.

Minimum dual-target attempt fields:

- `campaign_id`, `attempt_index`, `mode`
- `x`, `y`, `z`, plus machine coordinates for the EMFI probe
- `slots.dut.project_id`, `slots.dut.build_sha`
- `slots.platform.project_id`, `slots.platform.build_sha`
- `timing_reference.source`, `timing_reference.edge`
- `emfi.commanded_delay_us`, `emfi.commanded_width_ns`,
  `emfi.commanded_voltage_v`, and any ChipSHOUTER read-back width/state
- `crowbar.commanded_delay_us`, `crowbar.commanded_width_ns`,
  `crowbar.output`, and Husky status/error fields
- `timeline_actual` if either device can report measured or quantized timing
- `verdicts.dut` and `verdicts.platform`
- `outcome`, with room for combined categories such as `dut_glitch`,
  `platform_glitch`, `combined_glitch`, `crash`, `hang`, and `nothing`
- `stop_reason` when an attempt ends the campaign

Keep the existing top-level `glitch_delay_us`, `pulse_width_ns`, and
`shouter_voltage` for compatibility with current heatmaps. For dual-target
runs, populate those from the EMFI action and add crowbar-specific fields in a
nested object.

Campaign-level logs should also record:

- full submitted campaign JSON;
- preflight result;
- flashed provenance snapshot for each slot;
- device connection snapshot;
- auth principal and source client;
- git revision of Control and Develop.

## UI expectations

The first View implementation can stay simple:

- campaign mode selector: `single target` or `dual target`;
- two slot panels showing firmware build, power rail, UART, programmer, and
  glitcher;
- EMFI grid controls remain attached to the DUT slot;
- timeline table with one EMFI row and one crowbar row;
- attempt estimate that multiplies all enabled sweep dimensions;
- preflight panel that lists blocking failures and warnings by slot/device;
- run page that can filter outcomes by DUT, Platform, or combined result.

## Implementation status

1. [x] Add protocol models for `mode`, `slots`, `timing.timeline`, named `sweeps`,
   and `budgets` while preserving current `Campaign` compatibility.
2. [ ] Track last flashed provenance per slot in Control.
3. [ ] Extend preflight to validate both slots, rail policy, Husky readiness,
   and the full timeline.
4. [x] Add a Husky adapter with status/configure/crowbar-pulse route shape.
5. [ ] Replace the Husky stub with real ChipWhisperer connect/configure/pulse
   behavior.
6. [ ] Teach the orchestrator to program both timing paths per attempt.
7. [ ] Extend attempt logging and CSV export for nested EMFI/crowbar data.
8. [ ] Add View controls and dual-target run analysis.

Do the protocol and preflight work before adding UI polish. If Control cannot
reject an unsafe dual-target campaign without touching hardware, it is not ready
for AI-launched experiments.
