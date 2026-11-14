#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out="$task_root/build/boot-latency-loader"
test -d "$out"
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin \
    -Os -marm -march=armv7-a -Wall -Wextra -Werror -I"$out" \
    -Wl,-Ttext=0x4be00 -Wl,--build-id=none -Wl,-e,boot_crc_fast \
    -o "$out/crc-hook.elf" "$task_root/firmware/boot_crc_fast.c"
arm-none-eabi-objcopy -O binary "$out/crc-hook.elf" "$out/crc-hook.bin"
arm-none-eabi-objdump -d "$out/crc-hook.elf" > "$out/crc-hook.disassembly.txt"
arm-none-eabi-size "$out/crc-hook.elf"
