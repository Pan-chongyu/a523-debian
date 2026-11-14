#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-rtc-log"
mkdir -p "$out" "$task_root/build/rtc-log"
cp "$task_root/firmware/tzx_rtc_log.c" "$out/"
printf 'obj-m := tzx_rtc_log.o\n' > "$out/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-cpufreq-framework-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_rtc_log.ko" "$task_root/build/rtc-log/"
sha256sum "$task_root/build/rtc-log/tzx_rtc_log.ko"
