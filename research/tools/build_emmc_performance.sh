#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-emmc-performance"
mkdir -p "$out" "$task_root/build/emmc-performance"
cp "$task_root/firmware/tzx_emmc_performance.c" "$out/"
printf 'obj-m := tzx_emmc_performance.o\nccflags-y := -I%s/linux-7.3.3/drivers/mmc/core\n' "$base" > "$out/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-screen-boot-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_emmc_performance.ko" "$task_root/build/emmc-performance/"
sha256sum "$task_root/build/emmc-performance/tzx_emmc_performance.ko"
