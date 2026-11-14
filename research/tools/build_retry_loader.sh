#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -fno-builtin -fno-short-enums \
    -Os -march=armv7ve -ffunction-sections -fdata-sections \
    -DCOLD_BOOT -DCHAIN_BOOT -DSPEED_1BIT_FAST -I"$task_root/build" \
    -Wl,-T,"$task_root/firmware/dram.ld" -Wl,--build-id=none -Wl,--gc-sections \
    -Wl,-Map,"$task_root/build/chain-retry.map" -o "$task_root/build/chain-retry.elf" \
    "$task_root/firmware/cold_retry_entry.S" "$task_root/firmware/enter_arm64.S" \
    "$task_root/firmware/dram_probe.c" "$task_root/firmware/chain_retry_loader.c" \
    "$task_root/firmware/emmc_retry_reader.c" \
    "$task_root/upstream/SyterKit/soc/sun55iw3/lib/libdram.a" -lgcc
arm-none-eabi-objcopy -O binary "$task_root/build/chain-retry.elf" "$task_root/build/chain-retry.bin"
arm-none-eabi-size "$task_root/build/chain-retry.elf"
arm-none-eabi-nm -n "$task_root/build/chain-retry.elf" | tail -n 12
