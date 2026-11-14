#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-cpu-cooling"
mkdir -p "$out" "$task_root/build/cpu-cooling"
cp "$task_root/firmware/tzx_cpu_cooling.c" "$out/"
printf 'obj-m := tzx_cpu_cooling.o\n' > "$out/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-cpufreq-framework-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_cpu_cooling.ko" "$task_root/build/cpu-cooling/"
sha256sum "$task_root/build/cpu-cooling/tzx_cpu_cooling.ko"
