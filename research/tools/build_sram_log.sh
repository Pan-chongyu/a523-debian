#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-sram-log"
mkdir -p "$out" "$task_root/build/sram-log"
cp "$task_root/firmware/tzx_sram_log.c" "$out/"
printf 'obj-m := tzx_sram_log.o\n' > "$out/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-cpufreq-framework-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_sram_log.ko" "$task_root/build/sram-log/"
sha256sum "$task_root/build/sram-log/tzx_sram_log.ko"
