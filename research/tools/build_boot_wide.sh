#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out="$task_root/build/boot-wide-emmc"
mkdir -p "$out"
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin \
    -Os -marm -march=armv7-a -Wall -Wextra -Werror \
    -Wl,-Ttext=0x4c500 -Wl,--build-id=none -Wl,-e,boot_emmc_wide \
    -Wl,--defsym,udelay=0x44134 \
    -o "$out/wide-hook.elf" "$task_root/firmware/boot_emmc_wide.c"
arm-none-eabi-objcopy -O binary "$out/wide-hook.elf" "$out/wide-hook.bin"
arm-none-eabi-objdump -d "$out/wide-hook.elf" > "$out/wide-hook.disassembly.txt"
arm-none-eabi-size "$out/wide-hook.elf"
