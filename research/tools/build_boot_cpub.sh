#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out="$task_root/build/boot-early-cpub"
mkdir -p "$out"
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin \
    -Os -marm -march=armv7-a -Wall -Wextra -Werror \
    -Wl,-Ttext=0x4c300 -Wl,--build-id=none -Wl,-e,boot_cpub_early \
    -Wl,--defsym,udelay=0x44134 \
    -o "$out/cpub-hook.elf" "$task_root/firmware/boot_cpub_early.c"
arm-none-eabi-objcopy -O binary "$out/cpub-hook.elf" "$out/cpub-hook.bin"
arm-none-eabi-objdump -d "$out/cpub-hook.elf" > "$out/cpub-hook.disassembly.txt"
arm-none-eabi-size "$out/cpub-hook.elf"
