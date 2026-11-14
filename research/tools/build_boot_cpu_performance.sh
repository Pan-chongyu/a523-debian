#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out="$task_root/build/boot-cpu-performance"
mkdir -p "$out"
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin -fno-common \
    -Os -marm -march=armv7-a -Wall -Wextra -Werror \
    -Wl,-Ttext=0x4e200 -Wl,--build-id=none -Wl,-e,boot_cpu_performance_init \
    -Wl,--defsym,udelay=0x44134 -Wl,-Map,"$out/cpu-hook.map" \
    -o "$out/cpu-hook.elf" "$task_root/firmware/boot_cpu_performance.c"
arm-none-eabi-objcopy -O binary "$out/cpu-hook.elf" "$out/cpu-hook.bin"
arm-none-eabi-objdump -d "$out/cpu-hook.elf" > "$out/cpu-hook.disassembly.txt"
arm-none-eabi-nm -n "$out/cpu-hook.elf" > "$out/cpu-hook.symbols.txt"
arm-none-eabi-size "$out/cpu-hook.elf"
