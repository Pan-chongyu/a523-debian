#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out="$task_root/build/boot-hwcrc"
mkdir -p "$out"
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin \
    -Os -marm -march=armv8-a+crc -Wall -Wextra -Werror \
    -Wl,-Ttext=0x4ce00 -Wl,--build-id=none -Wl,-e,boot_crc_hw \
    -o "$out/hwcrc-hook.elf" "$task_root/firmware/boot_crc_hw.c"
arm-none-eabi-objcopy -O binary "$out/hwcrc-hook.elf" "$out/hwcrc-hook.bin"
arm-none-eabi-objdump -d "$out/hwcrc-hook.elf" > "$out/hwcrc-hook.disassembly.txt"
arm-none-eabi-size "$out/hwcrc-hook.elf"
