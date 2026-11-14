#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-gpu-performance"
mkdir -p "$out" "$task_root/build/gpu-performance"
cp "$task_root/firmware/tzx_gpu_performance.c" "$out/"
printf 'obj-m := tzx_gpu_performance.o\n' > "$out/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-cpufreq-framework-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_gpu_performance.ko" "$task_root/build/gpu-performance/"
sha256sum "$task_root/build/gpu-performance/tzx_gpu_performance.ko"
