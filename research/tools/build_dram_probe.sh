#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin -Os -march=armv7-a \
    -Wl,-T,"$task_root/firmware/dram.ld" -Wl,--build-id=none \
    -o "$task_root/build/dram-probe.elf" "$task_root/firmware/dram_entry.S" \
    "$task_root/firmware/dram_probe.c" "$task_root/upstream/SyterKit/soc/sun55iw3/lib/libdram.a" -lgcc
arm-none-eabi-objcopy -O binary "$task_root/build/dram-probe.elf" "$task_root/build/dram-probe.bin"
arm-none-eabi-size "$task_root/build/dram-probe.elf"
sha256sum "$task_root/build/dram-probe.bin"
