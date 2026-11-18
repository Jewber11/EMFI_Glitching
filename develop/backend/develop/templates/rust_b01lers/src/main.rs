#![no_std]
#![no_main]

// Minimal Rust target firmware for MSPM0L2228 against b01lers' eCTF HAL.
//
// Pin mapping (mirrors the C template):
//   PA21 USER_TEST       → D0
//   PB14 USER_HEARTBEAT  → D1
//   PB10 USER_LED_2      → D2
//   PB9  USER_LED_3      → D3

use cortex_m_rt::entry;

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[entry]
fn main() -> ! {
    // TODO:
    // 1. Init clock + GPIO via b01lers_mspm0_hal
    // 2. Glitch-target loop: assert PA21, run the target sequence,
    //    pulse PB10 on detected fault, toggle PB14 each iteration
    let mut counter: u32 = 0;
    loop {
        counter = counter.wrapping_add(1);
        core::hint::black_box(&counter);
    }
}
