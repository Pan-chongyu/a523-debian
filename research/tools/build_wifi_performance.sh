#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-7.3.3"
out="$base/tzx-wifi-performance"
artifacts="$task_root/build/wifi-performance"
mkdir -p "$out"
cp "$artifacts/tzx_wifi_runtime.c" "$out/"
printf 'obj-m := tzx_wifi_runtime.o\nccflags-y := -I%s/drivers/mmc/core\n' "$source" > "$out/Makefile"
make -C "$source" O="$base/kernel-cpufreq-framework-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_wifi_runtime.ko" "$artifacts/"
sha256sum "$artifacts/tzx_wifi_runtime.ko"
