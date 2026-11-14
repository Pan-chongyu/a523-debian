#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out="$task_root/build/boot-logo"
mkdir -p "$out"
for part in logo loader; do
    if [ "$part" = logo ]; then address=0x42000000; entry=boot_logo_show; source=boot_logo.c
    else address=0x4e900; entry=boot_logo_init; source=boot_logo_loader.c; fi
    arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin -fno-common \
        -Os -marm -march=armv7-a -Wall -Wextra -Werror -I"$out" \
        -Wl,-Ttext="$address" -Wl,--build-id=none -Wl,-e,"$entry" \
        -Wl,--defsym,udelay=0x44134 -Wl,-Map,"$out/$part.map" \
        -o "$out/$part.elf" "$task_root/firmware/$source"
    arm-none-eabi-objcopy -O binary "$out/$part.elf" "$out/$part.bin"
    arm-none-eabi-objdump -d "$out/$part.elf" > "$out/$part.disassembly.txt"
    arm-none-eabi-nm -n "$out/$part.elf" > "$out/$part.symbols.txt"
    arm-none-eabi-size "$out/$part.elf"
done
