#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out="$task_root/build/boot-icache"
mkdir -p "$out"
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin \
    -Os -marm -march=armv7-a -Wall -Wextra -Werror \
    -Wl,-Ttext=0x4ce00 -Wl,--build-id=none -Wl,-e,boot_icache_init \
    -o "$out/icache-hook.elf" "$task_root/firmware/boot_icache.c"
arm-none-eabi-objcopy -O binary "$out/icache-hook.elf" "$out/icache-hook.bin"
arm-none-eabi-objdump -d "$out/icache-hook.elf" > "$out/icache-hook.disassembly.txt"
arm-none-eabi-nm -n "$out/icache-hook.elf" > "$out/icache-hook.symbols.txt"
arm-none-eabi-size "$out/icache-hook.elf"
