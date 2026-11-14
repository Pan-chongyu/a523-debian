#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin -Os -march=armv7-a \
    -ffunction-sections -fdata-sections -DSPEED_1BIT_FAST \
    -Wl,-Ttext=0x20000 -Wl,-e,checked_entry -Wl,--build-id=none -Wl,--gc-sections \
    -o "$task_root/build/fel-checked-reader.elf" "$task_root/firmware/fel_checked_reader.c" -lgcc
arm-none-eabi-objcopy -O binary "$task_root/build/fel-checked-reader.elf" "$task_root/build/fel-checked-reader.bin"
arm-none-eabi-size "$task_root/build/fel-checked-reader.elf"
