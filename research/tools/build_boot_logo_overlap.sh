#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out="$task_root/build/boot-logo-overlap"
mkdir -p "$out"
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin -fno-common \
    -Os -marm -march=armv7-a -DTZX_PANEL_OVERLAP -Wall -Wextra -Werror \
    -Wl,-Ttext=0x4d000 -Wl,--build-id=none -Wl,-e,boot_panel_voltage_entry \
    -Wl,--section-start=.rodata=0x4ef00 \
    -Wl,--defsym,udelay=0x44134 -Wl,-Map,"$out/panel.map" \
    -o "$out/panel.elf" "$task_root/firmware/boot_panel_early.c"
arm-none-eabi-objcopy -O binary -j .text "$out/panel.elf" "$out/panel-text.bin"
arm-none-eabi-objcopy -O binary -j .rodata "$out/panel.elf" "$out/panel-rodata.bin"
arm-none-eabi-objdump -d "$out/panel.elf" > "$out/panel.disassembly.txt"
arm-none-eabi-nm -n "$out/panel.elf" > "$out/panel.symbols.txt"
arm-none-eabi-size "$out/panel.elf"
panel_entry=$(arm-none-eabi-nm "$out/panel.elf" | awk '$3=="boot_panel_voltage_entry" { print "0x"$1 }')
panel_finish=$(arm-none-eabi-nm "$out/panel.elf" | awk '$3=="boot_panel_finish" { print "0x"$1 }')
panel_cancel=$(arm-none-eabi-nm "$out/panel.elf" | awk '$3=="boot_panel_cancel" { print "0x"$1 }')
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin -fno-common \
    -Os -marm -march=armv7-a -DTZX_PANEL_OVERLAP -Wall -Wextra -Werror \
    -Wl,-Ttext=0x4eac0 -Wl,--build-id=none -Wl,-e,boot_panel_performance_entry \
    -Wl,--defsym,original_panel_voltage="$panel_entry" \
    -Wl,--defsym,boot_panel_finish="$panel_finish" \
    -Wl,--defsym,boot_panel_cancel="$panel_cancel" \
    -Wl,--defsym,original_cpu_boost=0x4e6a4 \
    -Wl,--defsym,original_card_init=0x4c700 \
    -Wl,--defsym,original_cpu_restore=0x4e5e0 \
    -Wl,-Map,"$out/speed.map" \
    -o "$out/speed.elf" "$task_root/firmware/boot_logo_speed.c"
arm-none-eabi-objcopy -O binary "$out/speed.elf" "$out/speed.bin"
arm-none-eabi-objdump -d "$out/speed.elf" > "$out/speed.disassembly.txt"
arm-none-eabi-nm -n "$out/speed.elf" > "$out/speed.symbols.txt"
arm-none-eabi-size "$out/speed.elf"
