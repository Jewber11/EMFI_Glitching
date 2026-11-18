/* MSPM0L2228 standalone image. Adjust regions for a bootloader application. */
MEMORY
{
  FLASH : ORIGIN = 0x00000000, LENGTH = 256K
  RAM : ORIGIN = 0x20200000, LENGTH = 32K
}
