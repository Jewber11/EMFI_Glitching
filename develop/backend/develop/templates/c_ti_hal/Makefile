# Minimal MSPM0L2228 build using arm-none-eabi-gcc.
# Replace MSPM0_SDK with the path to your TI MSPM0 SDK on the lab box.

CC      = arm-none-eabi-gcc
OBJCOPY = arm-none-eabi-objcopy
OBJDUMP = arm-none-eabi-objdump

CFLAGS  = -mcpu=cortex-m0plus -mthumb -Os -ffunction-sections -fdata-sections \
          -Wall -Wextra -g3
LDFLAGS = -Tlinker.ld -nostartfiles -Wl,--gc-sections

SRC = $(wildcard src/*.c)
OBJ = $(SRC:.c=.o)

all: firmware.elf firmware.bin firmware.lst

firmware.elf: $(OBJ)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $^

firmware.bin: firmware.elf
	$(OBJCOPY) -O binary $< $@

firmware.lst: firmware.elf
	$(OBJDUMP) -d -S $< > $@

clean:
	rm -f $(OBJ) firmware.elf firmware.bin firmware.lst

.PHONY: all clean
