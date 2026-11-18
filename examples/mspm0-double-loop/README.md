# MSPM0L2228 double-loop target

This standalone workload repeatedly counts 256 × 256 iterations and reports
`normal` or `ESCAPED` over UART0. A fault that does not alter the checked
values can go undetected. A corrupted loop counter may hang the target.

Build `main.c` in a TI MSPM0 SDK project with `SYSCFG_DL_init()` and `UART_0_INST`
configured for UART0, PA10 TX, PA11 RX, 115200 baud, 8N1. The local
`../firmware/2026-attack-firmware/insecureExample/firmware` project contains
an example generated configuration, but its application/linker layout is for
an eCTF bootloader. Use the correct linker and packaging for the actual board;
do not overwrite a bootloader that must be preserved. This example has not been
built or tested on hardware.

Connect target PA10 to the USB UART RX and common ground. In Campaign Advanced,
select that UART, 115200 baud, normal text `normal`, glitch text `ESCAPED`, and
a verdict window long enough to receive at least one complete line. Confirm
clean continuous `normal` output before scanning. The built-in observer clears
the UART buffer before each pulse and checks output afterward; incomplete or
missing output can be classified as crash or hang. Reset and recheck a hung
target before continuing.

Home with clearance, calibrate the chip corners and Z height, then configure the
XY grid, pulse-width range, and attempts per point. Preflight and start the
campaign from the dashboard. It snakes across the grid and tries every selected
pulse width at each point, saving outcomes in the run log and heatmap. FaultyCat
currently supports immediate software pulses only; delay and voltage sweeps and
precise synchronization to the loop are unavailable. This free-running target
therefore samples random loop phases, rather than a repeatable delay after a
trigger. Do not start a scan until the physical bounds and clearance are checked.
