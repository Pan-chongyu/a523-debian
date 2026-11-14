#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$task_root/build/cpu-stream-probe"
mkdir -p "$out"
cp "$task_root/firmware/tzx_cpu_stream_probe.c" "$out/"
printf 'obj-m += tzx_cpu_stream_probe.o\n' > "$out/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-cpufreq-framework-build" ARCH=arm64 \
    CROSS_COMPILE=aarch64-linux-gnu- M="$out" modules
sha256sum "$out/tzx_cpu_stream_probe.ko"
