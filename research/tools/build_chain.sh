#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin -fno-short-enums -Os -march=armv7-a \
    -ffunction-sections -fdata-sections -DCOLD_BOOT -DCHAIN_BOOT -DSPEED_1BIT_FAST -I"$task_root/build" \
    -Wl,-T,"$task_root/firmware/dram.ld" -Wl,--build-id=none -Wl,--gc-sections \
    -Wl,-Map,"$task_root/build/chain-loader.map" \
    -o "$task_root/build/chain-loader.elf" "$task_root/firmware/cold_dram_entry.S" \
    "$task_root/firmware/enter_arm64.S" "$task_root/firmware/dram_probe.c" \
    "$task_root/firmware/chain_loader.c" "$task_root/firmware/emmc_reader.c" \
    "$task_root/upstream/SyterKit/soc/sun55iw3/lib/libdram.a" -lgcc
arm-none-eabi-objcopy -O binary "$task_root/build/chain-loader.elf" "$task_root/build/chain-loader.bin"
arm-none-eabi-size "$task_root/build/chain-loader.elf"
aarch64-linux-gnu-gcc -static -fno-pie -no-pie -nostdlib -nostartfiles -Wl,-Ttext=0x4a000000 -Wl,--build-id=none \
    -o "$task_root/build/linux-entry.elf" "$task_root/firmware/linux_entry.S"
aarch64-linux-gnu-objcopy -O binary "$task_root/build/linux-entry.elf" "$task_root/build/linux-entry.bin"
cp /opt/a523-debian-20261109/jernej-atf/build/sun55i_a523/debug/bl31.bin "$task_root/build/bl31.bin"
