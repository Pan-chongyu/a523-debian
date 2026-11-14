#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-7.3.3"
out="$base/tzx-wifi-bus-trial"
artifacts="$task_root/build/wifi-bus-trial"
mkdir -p "$out"
cp "$artifacts/tzx_wifi_runtime.c" "$out/"
printf 'obj-m := tzx_wifi_runtime.o\nccflags-y := -I%s/drivers/mmc/core\n' "$source" > "$out/Makefile"
make -C "$source" O="$base/kernel-cpu-tlbi-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j8 modules
cp "$out/tzx_wifi_runtime.ko" "$artifacts/"
sha256sum "$artifacts/tzx_wifi_runtime.ko"
