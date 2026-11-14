#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-cpu-dvfs"
mkdir -p "$out" "$task_root/build/cpu-dvfs"
cp "$task_root/build/cpu-dvfs/source/"*.c "$out/"
printf 'obj-m := tzx_cpufreq_dvfs.o tzx_cpu_dvfs_cooling.o\n' > "$out/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-screen-boot-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/"*.ko "$task_root/build/cpu-dvfs/"
sha256sum "$task_root/build/cpu-dvfs/"*.ko
