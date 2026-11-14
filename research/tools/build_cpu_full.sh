#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
module="$base/tzx-cpu-full"
artifacts="$task_root/build/cpu-full"
mkdir -p "$module" "$artifacts"
cp "$task_root/firmware/tzx_cpufreq_dvfs_v2.c" "$task_root/firmware/tzx_cpu_dvfs_cooling_v2.c" "$module/"
printf 'obj-m := tzx_cpufreq_dvfs_v2.o tzx_cpu_dvfs_cooling_v2.o\n' > "$module/Makefile"
make -C "$base/linux-hs-source" O="$base/kernel-hs-build" M="$module" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$module/"*.ko "$artifacts/"
sha256sum "$artifacts/"*.ko
