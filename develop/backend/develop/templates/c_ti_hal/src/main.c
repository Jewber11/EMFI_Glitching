/* Minimal MSPM0L2228 target firmware for the Scaffold-driven glitch rig.
 *
 * Pin mapping (matches the lab's standard wiring; see old-em-setup HANDOFF):
 *   PA21 USER_TEST       → D0 (rising edge = test loop start)
 *   PB14 USER_HEARTBEAT  → D1 (toggled regularly = heartbeat alive)
 *   PB10 USER_LED_2      → D2 (rising edge = target self-detected fault)
 *   PB9  USER_LED_3      → D3 (falling edge = campaign end marker)
 *
 * This is a placeholder — wire in your MSPM0 SDK headers + clock/GPIO init.
 */

/* TODO: include <ti/devices/msp/msp.h> or vendor's MSPM0 headers */

static volatile unsigned int counter;

int main(void) {
    /* TODO:
     * 1. ClockSetup() — switch to PLL, set MCU clock per chosen frequency
     * 2. GPIOInit() — set PA21, PB14, PB10, PB9 as outputs
     * 3. main loop:
     *      - assert PA21 (test start)
     *      - run the glitch-target sequence (compute / check / branch)
     *      - if fault detected: pulse PB10 high
     *      - toggle PB14 (heartbeat)
     *      - at campaign end: drive PB9 low
     */
    while (1) {
        counter++;
        /* glitch-target code goes here */
    }
    return 0;
}
