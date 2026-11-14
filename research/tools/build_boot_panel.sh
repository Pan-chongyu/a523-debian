#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out="$task_root/build/boot-panel-early-v2"
mkdir -p "$out"
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin -fno-common \
    -Os -marm -march=armv7-a -Wall -Wextra -Werror \
    -Wl,-Ttext=0x4d000 -Wl,--build-id=none -Wl,-e,boot_panel_voltage_entry \
    -Wl,--defsym,udelay=0x44134 -Wl,-Map,"$out/panel-hook.map" \
    -o "$out/panel-hook.elf" "$task_root/firmware/boot_panel_early.c"
arm-none-eabi-objcopy -O binary "$out/panel-hook.elf" "$out/panel-hook.bin"
arm-none-eabi-objdump -d "$out/panel-hook.elf" > "$out/panel-hook.disassembly.txt"
arm-none-eabi-nm -n "$out/panel-hook.elf" > "$out/panel-hook.symbols.txt"
arm-none-eabi-size "$out/panel-hook.elf"
