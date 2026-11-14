#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
mkdir -p "$base/tzx-wifi-module"
cp "$task_root/firmware/tzx_wifi_runtime.c" "$base/tzx-wifi-module/"
printf 'obj-m := tzx_wifi_runtime.o\nccflags-y := -I%s/drivers/mmc/core\n' \
    "$base/linux-7.3.3" > "$base/tzx-wifi-module/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-build" M="$base/tzx-wifi-module" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j8 modules
cp "$base/tzx-wifi-module/tzx_wifi_runtime.ko" "$task_root/build/"
