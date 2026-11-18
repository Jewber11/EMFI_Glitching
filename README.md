# Ender 3 + FaultyCat EMFI platform

Control, Develop, View and the shared protocol come from EM-Architecture. Control drives an Ender 3 running Marlin over USB and a FaultyCat v3 over its EMFI CDC interface. View provides calibration, jogging, campaigns, live position, runs and heatmaps. Develop remains available for firmware projects and target-specific host scripts.

## Install and start

Requirements: Python 3.11+, Node.js 20+ with npm, the adjacent `../faultycat-tools` checkout, and serial-port access for your user.

```sh
python3 -m venv .venv
.venv/bin/pip install -e ./protocol -e './control[dev]' -e './develop[dev]' -e ../faultycat-tools
(cd view && npm ci)
(cd develop/frontend && npm ci && npm run build)
./start.sh
```

This workspace includes a local Node.js installation under `.tools/node`; `start.sh` uses it if npm is absent from PATH.

Open <http://127.0.0.1:8003>. Control listens on port 8001 and Develop on 8002. `start.sh` binds locally. The firmware tools and MSPM0 development features in Develop still require their target-specific toolchains.

For Pico Debug Probe and 2026 eCTF firmware flashing, see [Pico flashing setup](docs/pico-flashing.md).

## Rig operation

1. Connect the printer and FaultyCat. Control retries discovery every five seconds. The FaultyCat vendor discovery selects the EMFI interface. The printer uses 115200 baud and is auto-selected when exactly one configured USB match exists. Use **Devices** on the dashboard to select ports manually when needed; selected ports are saved. Historical API keys `chipshover` and `chipshouter` refer to Ender 3 and FaultyCat.
2. Home the printer only when the probe and fixture have clearance. Jog to the scan origin and set it in **Calibrate**. Choose the opposite corner and grid spacing. Verify jog directions and Z clearance before starting. Homing clears the origin.
3. Arm the global gate and enable FaultyCat. Configure a campaign or use the manual pulse button. FaultyCat pulse width is 1–50 µs in whole microseconds. Each shot charges, fires and waits for completion. The dashboard and API represent widths in nanoseconds (1000–50000 in steps of 1000).
4. Optional: enter a target UART port, baud, normal-response text and glitch-response text in campaign Advanced settings. The input buffer is cleared before each pulse and read for the verdict window afterward. Matching glitch text is a glitch; matching normal text is nothing; no response is a hang; other responses are crashes. A project `host/run.py` can implement target-specific setup, stimulus, observation and teardown. Without either, shots are recorded as **unobserved**, not simulated results.
5. Stop or disarm from the dashboard. Run history and heatmaps use the Control logbook in `~/.local/share/emfi-control/`.

Only immediate software triggering is integrated. FaultyCat voltage and delay sweeps and ChipSHOUTER-specific controls are unavailable. Scaffold, XDS110 and AD2 integrations remain optional source features. The old desktop applications remain in the repository as references.

Run rig tests with `.venv/bin/pytest control/tests/test_rig_integration.py control/tests/test_faultycat_adapter.py control/tests/test_ender3_adapter.py control/tests/test_motion_fixture.py control/tests/test_safety.py`. Tests use simulated devices; actual printer movement and FaultyCat firing must be verified on the connected rig.
