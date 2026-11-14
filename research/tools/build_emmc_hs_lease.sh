#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-emmc-hs-lease"
mkdir -p "$out" "$task_root/build/hs-kernel"
cp "$task_root/firmware/tzx_emmc_hs_lease.c" "$task_root/firmware/tzx_emmc_hs.h" "$out/"
printf 'obj-m := tzx_emmc_hs_lease.o\nccflags-y := -I%s/linux-hs-source/drivers/mmc/core\n' "$base" > "$out/Makefile"
make -C "$base/linux-hs-source" O="$base/kernel-hs-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_emmc_hs_lease.ko" "$task_root/build/hs-kernel/"
sha256sum "$task_root/build/hs-kernel/tzx_emmc_hs_lease.ko"
