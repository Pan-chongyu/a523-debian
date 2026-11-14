#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
module="$task_root/build/cpufreq-divider-v2"
mkdir -p "$module"
cp "$task_root/firmware/tzx_cpufreq_divider.c" "$module/"
printf 'obj-m += tzx_cpufreq_divider.o\n' > "$module/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-cpufreq-framework-build" ARCH=arm64 \
    CROSS_COMPILE=aarch64-linux-gnu- M="$module" modules
sha256sum "$module/tzx_cpufreq_divider.c" "$module/tzx_cpufreq_divider.ko"
