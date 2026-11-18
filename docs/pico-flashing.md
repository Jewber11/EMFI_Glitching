# Pico Debug Probe and MSPM0L2228

Use Raspberry Pi Debug Probe firmware providing CMSIS-DAP. Wire SWDIO to target SWDIO, SWCLK to SWCLK, and ground to ground. Power the target separately at its specified voltage. Connect the probe UART TX/RX crossed to the target bootloader UART RX/TX and share ground for eCTF loading. Verify the board pinout before connecting.

Install [probe-rs](https://probe.rs/docs/getting-started/installation/) with MSPM0L2228 support and the [2026 eCTF tools](https://rules.ectf.mitre.org/2026/system/ectf_tools.html). Control automatically selects one connected Pico Debug Probe and uses the bundled `.tools` probe-rs binary when available. For explicit selection or UART loading, edit `~/.config/emfi-control/config.json`, retaining the other settings:

```json
"programmer": {
  "backend": "pico",
  "probe_rs_bin": "probe-rs",
  "probe": null,
  "power_cycle": false,
  "ectf_bin": "ectf",
  "ectf_port": "/dev/ttyACM0"
}
```

Restart Control. Set `probe` to `VID:PID:SERIAL` when multiple probes are connected. Set `power_cycle` true only when Scaffold controls DUT power. If `ectf_port` is unset, Control uses the detected Pico UART. Ensure USB permissions allow the Control service to access the probe and UART. Control detects the probe through its USB serial interface; this does not prove SWD wiring or target power.

Download the board-specific [2026 insecure bootloader](https://rules.ectf.mitre.org/2026/system/bootloader.html). For probe-rs, prepare a copy with `arm-none-eabi-objcopy --remove-section=.BCRConfig --remove-section=.BSLConfig insecure.out bootloader.out`; this follows the [2026 UIUC design workflow](https://github.com/sigpwny/2026-ectf-uiuc#mitre-bootloaders). In Develop, open a project, enter the absolute path on the Control host, select Pico SWD, and press Flash file. ELF, OUT and Intel HEX images must contain their intended addresses. Existing project builds use the selected programmer too. SWD programming can overwrite existing firmware and bootloader regions.

For eCTF images, enter the bootloader's update mode first (on LITO, hold S2 while resetting). Select eCTF UART, enter the image path and name, then press Flash file. This runs `ectf hw PORT reflash`, which erases the application, loads it, and starts it. Secure attack boards require images accepted by their installed bootloader; `.prot` files are not interchangeable across keys. The secure bootloader cannot be restored if erased. Avoid SWD programming on attack boards if it must be preserved. The Pico SWD connection alone cannot perform the UART bootloader protocol.

The same interface is available through `POST /target/flash` with `build_sha`, `elf_url`, `mode` (`swd` or `ectf`), and optional `name`. Paths resolve on the Control host. Flashing requires the `target:flash` scope. SWD flashing verifies the written data and resets the target. UART loading requires separate physical verification.

Open **Firmware** in the dashboard, enter a folder on the Control host, scan it, and select an image from any team subfolder. ELF/OUT/HEX and extensionless ELF files use SWD; BIN/PROT/HSM use the eCTF UART loader. Only images compatible with the target and installed bootloader will run. Flashing a selected image records its SHA-256. The Rust project template builds standalone MSPM0L2228 firmware with `thumbv6m-none-eabi`; adapt its memory layout and image packaging for eCTF bootloader applications.
