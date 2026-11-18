/* MSPM0L2228 memory layout — fill in from TI's reference linker script.
 * This is a placeholder; the V1 build-out should replace with the real
 * memory regions from the TI MSPM0 SDK.
 */

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x00000000, LENGTH = 256K
    SRAM  (rwx) : ORIGIN = 0x20000000, LENGTH = 32K
}

ENTRY(Reset_Handler)

SECTIONS
{
    .text : {
        KEEP(*(.isr_vector))
        *(.text*)
        *(.rodata*)
    } > FLASH

    .data : {
        *(.data*)
    } > SRAM AT > FLASH

    .bss : {
        *(.bss*)
        *(COMMON)
    } > SRAM
}
