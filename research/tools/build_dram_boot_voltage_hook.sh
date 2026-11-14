#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out="$task_root/build/dram-boot-voltage"
mkdir -p "$out"
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin -Os -marm -march=armv7-a \
    -Wall -Wextra -Werror -Wl,-Ttext=0x4b900 -Wl,--build-id=none \
    -Wl,--defsym,udelay=0x44134 -Wl,--defsym,printf_dram=0x44170 \
    -Wl,-e,dram_boot_voltage_hook -o "$out/voltage-hook.elf" \
    "$task_root/firmware/dram_boot_voltage_hook.c"
arm-none-eabi-objcopy -O binary "$out/voltage-hook.elf" "$out/voltage-hook.bin"
arm-none-eabi-size "$out/voltage-hook.elf"
sha256sum "$out/voltage-hook.bin"
