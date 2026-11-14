#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out="$task_root/build/boot-fast"
mkdir -p "$out"
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin \
    -Os -marm -march=armv7-a -Wall -Wextra -Werror \
    -Wl,-Ttext=0x4c700 -Wl,--build-id=none -Wl,-e,boot_emmc_pins \
    -Wl,--defsym,udelay=0x44134 \
    -o "$out/pins-hook.elf" "$task_root/firmware/boot_emmc_pins.c"
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin \
    -Os -marm -march=armv7-a -Wall -Wextra -Werror \
    -Wl,-Ttext=0x4cb00 -Wl,--build-id=none -Wl,-e,boot_crc_word \
    -o "$out/word-hook.elf" "$task_root/firmware/boot_crc_word.c"
for part in pins word; do
    arm-none-eabi-objcopy -O binary "$out/$part-hook.elf" "$out/$part-hook.bin"
    arm-none-eabi-objdump -d "$out/$part-hook.elf" > "$out/$part-hook.disassembly.txt"
    arm-none-eabi-size "$out/$part-hook.elf"
done
