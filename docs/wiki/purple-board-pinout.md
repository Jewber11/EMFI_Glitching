# Purple board pinout

This page records the current purple board target wiring as observed in the
repo on June 1, 2026. The source pinout is
`targets/MSPM0L2228-Scaffold/pinout.txt`; bench verification is still required
for UART timing, trigger semantics, and the XDS110/SWD handoff.

## Board role

- Target MCU: MSPM0L2228.
- DUT slot: the purple board currently under EMFI test.
- Platform slot: reserved for the second MSPM0L2228 platform board planned for
  the dual-target setup.
- Scaffold: owns target I/O, DUT/platform 3.3 V rail switching, and pgen0/A0
  hardware trigger routing.
- XDS110: owns MSPM0L2228 flash/debug over the SWD pins when attached.

## Scaffold power

| Rail | UI label | Scaffold API | Use |
|---|---|---|---|
| DUT | slot 1 | `dut` | Purple board target power |
| Platform | slot 2 | `platform` | Future platform board or aux powered fixture |
| Both | all | `all` | Coordinated power-cycle only when both slots are wired correctly |

Both rails are independent 3.3 V supplies through separate Scaffold FETs. The
Control dashboard power card maps directly to these rails. Power-cycle `dut`
before flashing through XDS110; avoid cycling `platform` until a platform board
is installed and its wiring has been checked.

## Current pinout

| Scaffold pin | MSPM0L2228 signal | Current intended use | Notes |
|---|---|---|---|
| D0 | PB.14 | Attempt trigger / pgen source candidate | Control hardware-trigger modes use D0 rising edge to start pgen0. This conflicts with older template comments that used PB14 as heartbeat. |
| D1 | RST | Reset line candidate | Older host scripts treat D1 as heartbeat input. Do not rely on D1 for heartbeat until the purple board firmware and host script are aligned. |
| D2 | PA.11 RX0 | UART0 RX | Direction name is from the MCU perspective: target RX0 receives data. Bench timing not verified. |
| D3 | PA.10 TX0 | UART0 TX | Candidate status/output UART. Automation docs currently mention D3 as `uart_status`; verify against firmware. |
| D4 | PA.9 RX1 | UART1 RX | Direction name is from the MCU perspective. Bench timing not verified. |
| D5 | PA.8 TX1 | UART1 TX | Candidate second UART output. Bench timing not verified. |
| D6 | PA.18 BSL | Bootloader select | Treat as a mode strap; avoid toggling during normal campaigns unless the firmware/programming flow calls for it. |
| D7 | PA.19 SWDIO | SWD data | XDS110 uses this during flash/debug. Keep Scaffold high-Z unless intentionally testing SWD access. |
| D8 | PA.5 HFXIN | High-frequency crystal input | Do not drive from Scaffold until the clocking plan is confirmed. |
| D9 | SWCLK | SWD clock | XDS110 uses this during flash/debug. Keep Scaffold high-Z unless intentionally testing SWD access. |

## UART runbook

As of June 1, 2026, the flashed DUT firmware is expected to expose traffic on
UART0 and a slightly different build may also use UART1. The pinout gives both
channels:

| UART | Target RX | Target TX | Scaffold pins |
|---|---|---|---|
| UART0 | PA.11 / RX0 | PA.10 / TX0 | D2 / D3 |
| UART1 | PA.9 / RX1 | PA.8 / TX1 | D4 / D5 |

When checking UART from the lab:

1. Confirm DUT power is on and the XDS110 is not holding the target halted.
2. Scope target TX first: D3 for UART0, D5 for UART1.
3. Decode common MSPM0 UART baud rates before changing firmware. The observed
   issue may be timing/baud rather than a wiring fault.
4. If sending data into the target, drive Scaffold D2 for UART0 RX or D4 for
   UART1 RX only after confirming voltage level and idle polarity.

## Trigger and pgen wiring

Control's hardware trigger path is implemented as:

```text
D0 rising edge -> Scaffold pgen0.start
Scaffold pgen0.out -> A0
A0 -> ChipSHOUTER external trigger input
```

For `one-shot` and `free-run` campaign modes, pgen0 emits one active-high A0
trigger pulse per D0 rising edge. The pgen delay is the per-attempt glitch
delay. The pgen width is only the A0 trigger high-time, not the ChipSHOUTER EMFI
pulse width.

For the current purple board pinout, D0 is `PB.14`. Verify that the flashed
firmware toggles PB14 at the exact attempt start before using hardware-triggered
campaigns. Until then, `software` trigger mode is the safer diagnostic path.

## XDS110 / SWD notes

- The MSPM0L2228 programming path is XDS110 over SWD, not a full JTAG chain in
  the current docs.
- The relevant purple board pins are D7/PA.19/SWDIO, D9/SWCLK, and likely
  D1/RST.
- Only one tool should own SWD at a time. Detach OpenOCD/debug sessions before
  flashing, and avoid Scaffold drives on D7 or D9 while XDS110 is attached.
- If the target appears silent after flashing, check whether the debugger left
  the core halted before assuming UART failure.

## Known unknowns

- Whether D0/PB14 is now the true attempt trigger or still a heartbeat signal.
- Whether D1/RST replaces the old D1 heartbeat signal in all host scripts.
- UART0 and UART1 baud rate, framing, idle level, and whether both are enabled
  in the currently flashed DUT image.
- Whether D3/TX0 is still intended to double as `uart_status` in automation
  metadata.
- Whether D8/PA.5/HFXIN is connected to a clock source on the board or only
  broken out for future use.
- Exact reset/BSL sequence for D1/RST and D6/PA.18/BSL during bootloader
  recovery.
- Physical A0 cable path from Scaffold to the ChipSHOUTER external trigger for
  this bench setup.
- Platform slot pinout for the second MSPM0L2228 board and the future
  ChipWhisperer Husky crowbar trigger wiring.
