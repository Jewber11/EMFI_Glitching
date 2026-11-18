# control/ — local setup (deployment-specific)

You are working in the Control app of a 3-app EMFI research platform. Control is the **hardware-singleton service** that owns every USB device on the rig. Read this before doing anything that talks to hardware or changes wire formats.

## Where this runs

The real deployment is a single Linux box on a trusted lab LAN.

| | |
|---|---|
| Host | `faultierHost2` at `10.164.9.112` (Kali rolling 2025.4, kernel 6.16, amd64) |
| User | `stephen` (in groups `dialout`, `plugdev`, `chipwhisperer`, `sudo`) |
| Repo | `/home/stephen/EM-Architecture/` — pulls main from `github.com/FaultingFish/EM-Architecture` |
| SSH alias | `ssh em-lab` (key auth via `~/.ssh/em_lab_box`) |
| Shared venv | `/home/stephen/EM-Architecture/.venv` (also `control/.venv` after first `start.sh`) |
| Deployment config | `/home/stephen/.config/emfi-control/config.json` |
| Logbook + SQLite | `/home/stephen/.local/share/emfi-control/sessions/` |
| Audit JSONL | `/home/stephen/.local/share/emfi-control/audit/audit-YYYYMMDD.jsonl` |
| Last flashed DUT provenance | `/home/stephen/.local/share/emfi-control/flashed_firmware.json` |
| Campaign notes/tags | `/home/stephen/.local/share/emfi-control/campaign_metadata.json` |
| Service logs | `/home/stephen/.local/share/emfi-control/logs/control.log` (rotating) |

Develop CLI is on the lab box at `~/.local/bin/claude`. UniFlash is at `~/ti/uniflash_9.4.1/dslite.sh`. OpenOCD is `/usr/bin/openocd` (0.12.0).

## Hardware that is plugged in *right now*

Probed read-only on 2026-05-27 and confirmed responsive. All paths are **pinned** in `~/.config/emfi-control/config.json` (`ports.*_override`), so the classifier guess is belt-and-suspenders.

| Device | Path | VID:PID | Identity | Live state at probe |
|---|---|---|---|---|
| ChipShover | `/dev/ttyACM0` | `03eb:2424` | `marlinfw.org` / "3D Printer" | position `(0.0, 11.0, 216.5)` |
| ChipSHOUTER | `/dev/ttyUSB1` | `0403:6015` | `NewAE` / `ChipSHOUTER Serial` | id `5LY0MB:2.0.3`, **disarmed**, set V=500 / measured=21, no faults |
| Scaffold | `/dev/ttyUSB0` | `0403:6014` | `Ledger` / `Scaffold` (firmware 0.9) | DUT power = 0 |
| XDS110 | `/dev/ttyACM1` + `/dev/ttyACM2` | `0451:bef3` | TI XDS110 (serial `M4321005`, CMSIS-DAP) | enumerated; talked to via dslite/openocd over libusb, **not** via the ttyACM nodes |
| AD2 | USB libdwf | `0403:6014` | Digilent Analog Discovery 2 | dashboard capture: Scope CH1 pulse monitor, DIO0 trigger/ref, DIO1 ledger clock |

**Two things diverge from the original config defaults** (the classifier in `DEFAULTS` was tuned to the previous rig):
- ChipShover here runs **Marlin** firmware, not Smoothie. The `chipshover` PyPI library handles both.
- Scaffold's USB manufacturer string is `Ledger`, not `FTDI`. The deployment config adds Ledger + product-string matches.

If you change `DEFAULTS` in `config.py`, mirror the broadened patterns there — otherwise a fresh install on this rig won't auto-classify.

## Hardware library gotchas (observed during install)

These caused real install failures and are worth a comment in any future install doc:

- **`chipshover` PyPI tarball is malformed.** Install from git: `pip install "chipshover @ git+https://github.com/newaetech/ChipShover-Python.git"`.
- **`chipshouter` has an undeclared `six` dependency.** `pip install six` after.
- **`donjon-scaffold` is fine from PyPI** (0.9.5 installed, chain module is available).
- **AD2 needs Digilent WaveForms.** Control imports no Python AD2 package; it
  loads `libdwf.so` directly. Install the WaveForms Debian package on any lab
  host that physically owns the AD2.

## Safety contract — non-negotiable

Carry-forward from `old-em-setup/HANDOFF.md` (read it if you haven't):

1. **Every pulse-emitting path calls `arm_gate.require_armed()`.** No exceptions, no shortcuts, no "just this once".
2. **Every pulse-emitting path acquires a `RateLimiter` token.** Default 10/s in `config.safety.max_pulses_per_sec`.
3. **Every hardware call goes through a `DeviceWorker`.** No raw pyserial reads from a route handler, ever.
4. **`ChipShouterAdapter.arm()` must be idempotent.** The upstream lib raises `Firmware_State_Exception` on double-arm.
5. **`ChipShouterAdapter.arm()` must time out.** `wait_for_arm()` can block forever if HV doesn't come up.
6. **Use Scaffold's public close API**, not `bus.ser.close()` (the old code did this and it was fragile).

`safety.py`, `workers.py`, `state.py`, `logbook.py`, `ports.py` are intentional verbatim ports from `old-em-setup/`. They survived real lab incidents. Do not "improve" them without explicit reason.

## How you actually run this app

```bash
ssh em-lab
cd ~/EM-Architecture/control
bash start.sh                 # default 0.0.0.0:8001, INFO logging
bash start.sh --reload        # dev hot-reload
bash start.sh --debug         # DEBUG logging
CONTROL_PORT=18001 bash start.sh   # custom port
```

`start.sh` self-bootstraps: if `control/.venv` is missing it creates one and installs `protocol/` + `control[dev]`. If you've already got the shared `~/EM-Architecture/.venv`, source it before running and `start.sh` will use it instead.

Smoke checks from anywhere on the LAN:
```
curl http://10.164.9.112:8001/docs
curl http://10.164.9.112:8001/openapi.json
```

## Tests

```bash
cd ~/EM-Architecture/control
PYTHONPATH=src:../protocol ../.venv/bin/python -m pytest
```
Hardware-touching tests carry `@pytest.mark.hw` and are skipped by default; run with `pytest -m hw` only if you mean it.

## Files you'll touch most

| File | Why |
|---|---|
| `src/control/orchestrator.py` | Campaign engine — `perform_attempt` + `run_campaign`. **Carry forward from `old-em-setup/glitchweb/backend/app/orchestrator.py`**; extend with delay/voltage/pulse-width sweep |
| `src/control/routers/*.py` | Hardware, safety, campaign, run, and target endpoints |
| `src/control/adapters/*.py` | Wrap the upstream libs. Each call runs inside a `DeviceWorker` |
| `src/control/adapters/xds110.py` | UniFlash for `flash()`, OpenOCD for `attach_debugger()` |
| `src/control/adapters/husky.py` | Stub ChipWhisperer Husky crowbar surface; not real hardware control yet |
| `src/control/adapters/ad2.py` | Digilent WaveForms capture for dashboard pulse/trigger/clock traces |
| `src/control/audit.py` | Append-only dangerous-action audit JSONL |
| `src/control/campaign_metadata.py` | Durable campaign notes/tags keyed by campaign id |
| `src/control/provenance.py` | Durable Control-side records such as last flashed DUT build |
| `tests/` | Focused unit/regression coverage; hardware tests are opt-in |

## Cross-app communication

The repo has a shared `agentConversation.md` at the root. Use it when:
- You change a Pydantic model in `protocol/` that Develop or View consumes
- You rename or change the shape of a WS topic
- You change an endpoint path
- You discover a hardware quirk other sessions should know about

Append, don't edit. Format documented in that file's header.

## Out of scope (Phase 2 — do not build)

USB camera overlay, click-to-jog calibration, continuous heartbeat watcher, delta-encoded WS broadcasts, cross-rig comparison, cloud archive, persistent "always armed" mode. These are listed in `ARCHITECTURE.md` § Phase 2; file them as ideas, don't implement.

## When in doubt

- `SPEC.md` is the authoritative API contract for this app.
- `/Users/sglombic/.claude/plans/i-am-looking-for-wiggly-quill.md` is the locked-in architecture plan (on the dev Mac).
- `../ARCHITECTURE.md` has the system rationale.
- `../old-em-setup/HANDOFF.md` (only present on the dev Mac, ignored from repo) has bug history. Worth a read for any unexpected hardware behavior.
- Ask before touching the safety primitives or rewriting carry-forward code.
