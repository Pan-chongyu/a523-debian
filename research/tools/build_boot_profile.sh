#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out="$task_root/build/boot-profile"
mkdir -p "$out"
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin \
    -Os -marm -march=armv7-a -Wall -Wextra -Werror \
    -Wl,-Ttext=0x4c500 -Wl,--build-id=none -Wl,-e,boot_profile_init \
    -o "$out/profile-hook.elf" "$task_root/firmware/boot_profile.c"
arm-none-eabi-objcopy -O binary "$out/profile-hook.elf" "$out/profile-hook.bin"
arm-none-eabi-objdump -d "$out/profile-hook.elf" > "$out/profile-hook.disassembly.txt"
arm-none-eabi-nm -n "$out/profile-hook.elf" > "$out/profile-hook.symbols.txt"
arm-none-eabi-size "$out/profile-hook.elf"
