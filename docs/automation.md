# Automation and AI access

The public hostname `emfi.ics.red` is useful for operators and for automation,
but Control can move hardware and trigger high-voltage equipment. Automation
must authenticate, be scoped, and use higher-level campaign endpoints rather
than raw pulse/motion endpoints wherever possible.

## Authentication layers

Use two layers:

1. Cloudflare Access protects `https://emfi.ics.red` for every caller.
2. The EMFI APIs should enforce an application-level automation token before
   any unattended agent is allowed to start campaigns.

Cloudflare Access service tokens are the right outer credential for agents.
Create a token per automation client and send it on every request:

```bash
curl https://emfi.ics.red/api/control/readyz \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET"
```

The application-level token should be an `Authorization: Bearer ...` token
checked by Control and Develop. Keep separate tokens for:

- read-only observers
- build/firmware agents
- campaign-launch agents
- operators with manual hardware privileges

Do not let an AI agent use a human browser session cookie as its credential.

Control and Develop bearer-token auth is opt-in for local lab development.
When `EMFI_AUTH_TOKENS` is unset, the apps remain LAN-trust services. Before
using unattended automation through the public hostname, set
`EMFI_AUTH_TOKENS` for both `emfi-control` and `emfi-develop`; each service
will ignore scopes that do not apply to it.

`EMFI_AUTH_TOKENS` is a JSON object keyed by either a plain bearer token or a
`sha256:<hex-digest>` token id. Each value is either a scope list or an object
with `name` and `scopes`:

```bash
export EMFI_AUTH_TOKENS='{
  "replace-with-long-random-observer-token": {
    "name": "observer-dashboard",
    "scopes": ["control:read", "develop:read"]
  },
  "replace-with-long-random-builder-token": {
    "name": "firmware-builder",
    "scopes": ["develop:read", "develop:write", "develop:build"]
  },
  "replace-with-long-random-campaign-token": {
    "name": "campaign-agent",
    "scopes": [
      "control:read",
      "target:flash",
      "campaign:preflight",
      "campaign:start",
      "campaign:stop",
      "develop:read",
      "develop:build"
    ]
  },
  "sha256:replace-with-token-sha256-hex-digest": {
    "name": "operator-console",
    "scopes": [
      "control:read",
      "control:write",
      "devices:write",
      "motion:write",
      "shouter:write",
      "safety:arm",
      "target:flash",
      "campaign:preflight",
      "campaign:start",
      "campaign:stop",
      "develop:read",
      "develop:write",
      "develop:build",
      "develop:agent"
    ]
  }
}'
```

Generate token values with a CSPRNG and keep them out of git. To store only a
hash in `EMFI_AUTH_TOKENS`, hash the token value and use the `sha256:` key:

```bash
TOKEN="$(openssl rand -base64 48)"
printf '%s' "$TOKEN" | shasum -a 256 | awk '{print $1}'
```

Recommended initial scope mapping:

| Scope | Allows |
|---|---|
| `control:read` | `GET /api/control/readyz`, `/arm_state`, `/config`, `/devices`, `/runs`, `/heatmap`, `/campaigns` |
| `devices:write` | Device connect/disconnect and Scaffold power set/cycle |
| `motion:write` | Stage motion, homing, origin, and opposite-corner calibration |
| `shouter:write` | Raw ChipSHOUTER config, arm/disarm, and pulse endpoints |
| `safety:arm` | Control arm/disarm gate endpoints |
| `target:flash` | Target flash/reset/debug attach/detach |
| `campaign:preflight` | Campaign preflight |
| `campaign:start` | Start campaigns and replay runs |
| `campaign:stop` | Stop active campaigns |
| `control:write` | Fallback for future non-GET Control routes that do not match a narrower scope |
| `develop:read` | Project, build, artifact, disassembly, template, preset, prompt, target, and git-log reads |
| `develop:write` | Project create/import/delete, file writes, presets, host scripts, and target annotations |
| `develop:build` | Firmware build trigger |
| `develop:agent` | Claude/agent endpoint and prompt routes |

Require exact scopes for dangerous operations instead of treating
`campaign:start`, `target:flash`, or `shouter:write` as aliases for broader
operator access. The implementation also accepts `*` and prefix wildcards such
as `campaign:*`, but public automation clients should use explicit scopes.

## Automation contract

Agents should call a narrow, auditable flow:

1. `GET /api/control/readyz`
2. `GET /api/develop/projects`
3. `POST /api/develop/projects/{id}/build`
4. `POST /api/control/target/flash`
5. `POST /api/control/campaigns/preflight`
6. `POST /api/control/arm` only when a policy allows unattended arming
7. `POST /api/control/campaigns`
8. `GET /api/control/campaigns/{id}`
9. `POST /api/control/campaigns/{id}/stop` on budget or safety condition

Avoid direct calls to raw hardware endpoints such as `/shouter/pulse`,
`/motion/move_abs`, and Scaffold power routes from autonomous agents. Those
should remain manual/operator or policy-gated endpoints.

Campaign requests may include optional stop policies under `stop_conditions`:

```json
{
  "stop_conditions": {
    "max_glitches": 5,
    "stop_on_first_crash": true,
    "max_runtime_seconds": 1800
  }
}
```

Control validates these fields at request parse time and enforces them between
attempts. For build provenance, include `build_sha` and pass `project_id` /
`project_version` on `POST /api/control/target/flash` when available. Control
records the last successful DUT flash in
`~/.local/share/emfi-control/flashed_firmware.json` and blocks campaign start
when a pinned campaign build does not match the recorded flashed build.

Agent-launched campaigns should also include `automation_policy`. Preflight
checks these hard caps before launch; unlike `stop_conditions`, these are
blocking admission rules rather than runtime stop rules:

```json
{
  "automation_policy": {
    "max_attempts": 10000,
    "max_runtime_seconds": 1800,
    "max_voltage": 450,
    "allowed_trigger_modes": ["one-shot"]
  }
}
```

`POST /api/control/campaigns/preflight` blocks when total attempts, estimated
minimum runtime at the configured pulse-rate limit, requested/swept voltage, or
trigger mode exceeds the submitted policy. If `automation_policy` is omitted,
preflight returns a warning because it cannot enforce automation-specific caps.

If a campaign sets `target_pc` and leaves `sweep.delay_us` unset, Control will
look up the matching GlitchTarget in `~/emfi-projects/<project-id>/targets.json`
and materialize a delay sweep from `expected_delay_cycles` to
`expected_delay_cycles_end`. Agents should still set an explicit `delay_us`
sweep when they need to override the target annotation.

## Audit trail

Control appends dangerous actions to daily JSONL files under
`~/.local/share/emfi-control/audit/`. Entries include action, method, path,
query string, status code, client address, timestamp, and the application
principal when bearer-token auth is enabled.

Audited routes include arm/disarm, raw ChipSHOUTER routes, motion routes,
Scaffold power routes, device connect/disconnect, target flash/debug/reset
routes, campaign start/stop, and replay. Treat this as the operator/agent
forensics source; the run logbook remains the source of truth for attempt
results.

Campaign notes and tags are stored by campaign id at
`GET/PUT /api/control/campaigns/{campaign_id}/metadata` and persisted in
`~/.local/share/emfi-control/campaign_metadata.json`. They are operator
annotations, separate from the attempt logbook and audit log. The Runs page can
filter loaded rows by tag after it fetches campaign metadata.

## Curl examples

These examples include both layers: Cloudflare Access service-token headers and
the EMFI application bearer token. They assume Caddy is routing
`/api/control/*` to Control and `/api/develop/*` to Develop.

```bash
export EMFI_ORIGIN="https://emfi.ics.red"
export CF_ACCESS_CLIENT_ID="service-token-client-id.access"
export CF_ACCESS_CLIENT_SECRET="service-token-client-secret"
export EMFI_AUTOMATION_TOKEN="replace-with-long-random-campaign-token"

curl -fsS "$EMFI_ORIGIN/api/control/readyz" \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  -H "Authorization: Bearer $EMFI_AUTOMATION_TOKEN"
```

Build firmware through Develop:

```bash
PROJECT_ID="mspm0l2228-demo"

curl -fsS -X POST "$EMFI_ORIGIN/api/develop/projects/$PROJECT_ID/build" \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  -H "Authorization: Bearer $EMFI_AUTOMATION_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"version":"automation-smoke"}'
```

Flash the target with a build artifact:

```bash
BUILD_SHA="replace-with-build-sha"

curl -fsS -X POST "$EMFI_ORIGIN/api/control/target/flash" \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  -H "Authorization: Bearer $EMFI_AUTOMATION_TOKEN" \
  -H "Content-Type: application/json" \
  --data "{
    \"build_sha\": \"$BUILD_SHA\",
    \"elf_url\": \"$EMFI_ORIGIN/api/develop/projects/$PROJECT_ID/builds/$BUILD_SHA/firmware.elf\"
  }"
```

Run preflight before starting a campaign:

```bash
curl -fsS -X POST "$EMFI_ORIGIN/api/control/campaigns/preflight" \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  -H "Authorization: Bearer $EMFI_AUTOMATION_TOKEN" \
  -H "Content-Type: application/json" \
  --data @campaign.json
```

Start a campaign only after preflight passes:

```bash
curl -fsS -X POST "$EMFI_ORIGIN/api/control/campaigns" \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  -H "Authorization: Bearer $EMFI_AUTOMATION_TOKEN" \
  -H "Content-Type: application/json" \
  --data @campaign.json
```

Stop a campaign on budget, timeout, or safety condition:

```bash
CAMPAIGN_ID="replace-with-campaign-id"

curl -fsS -X POST "$EMFI_ORIGIN/api/control/campaigns/$CAMPAIGN_ID/stop" \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  -H "Authorization: Bearer $EMFI_AUTOMATION_TOKEN"
```

## Remaining API improvements before unattended attacks

- Keep bearer-token middleware enabled on remote deployments.
- Extend campaign metadata from optional notes/tags into required unattended-run
  fields when policy demands it: operator/agent id, objective, target board,
  and target project/build.
- Add policy fields that are not implemented yet, such as allowed rails and an
  explicit max pulse-rate cap independent of Control's configured safety limit.
- Add read/query tooling for audit events so operators do not need to tail JSONL
  by hand.
- Add a read-only endpoint for live state so agents do not scrape WebSocket
  traffic when polling is enough.

## Dual-target scaffold status

The protocol now accepts `mode: "dual_target"` campaigns with `slots`,
`timing.timeline`, named `sweeps`, and `budgets`. Control also exposes a Husky
adapter/API scaffold that reports missing ChipWhisperer support or stub status
without touching real hardware.

Still missing before this is usable for real crowbar experiments:

- per-slot flashed provenance for both DUT and Platform;
- real ChipWhisperer Husky connect/configure/crowbar implementation;
- campaign orchestrator support for synchronized EMFI + Husky actions;
- View controls and analysis pages for dual-target runs.

## Future dual-target setup

The upcoming setup adds:

- DUT slot MSPM0L2228 targeted by EMFI through ChipSHOUTER.
- Platform slot MSPM0L2228 targeted by voltage glitching through a
  ChipWhisperer Husky crowbar path.
- eCTF firmware projects with coordinated target/platform behavior.

Model this explicitly instead of overloading the existing single-target fields:

```text
rig/
  devices:
    emfi: ChipSHOUTER + Scaffold pgen/A0
    voltage_glitch: ChipWhisperer Husky crowbar
    dut_programmer: XDS110
    platform_programmer: XDS110 or shared debug probe
  targets:
    dut:
      power_rail: scaffold.dut
      uart_status: D3
      swd: D7/D9
    platform:
      power_rail: scaffold.platform
      uart_status: TBD
      glitcher: husky
```

Campaigns should eventually support multiple synchronized actions per attempt:

```json
{
  "timeline": [
    {"at_us": 0, "device": "scaffold", "action": "wait_for_trigger", "source": "dut.D0"},
    {"at_us": 1.2, "device": "chipshouter", "action": "emfi_pulse"},
    {"at_us": 1.6, "device": "husky", "action": "crowbar_pulse"}
  ]
}
```

That should be a protocol change, not a one-off host-script convention, because
the UI, preflight checks, audit log, and analysis pages all need to understand
which target was attacked by which mechanism.
