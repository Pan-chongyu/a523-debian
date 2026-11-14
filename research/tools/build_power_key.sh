#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-power-key"
mkdir -p "$out" "$task_root/build/power-key"
cp "$task_root/firmware/tzx_power_key.c" "$out/"
printf 'obj-m := tzx_power_key.o\n' > "$out/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-acceleration-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_power_key.ko" "$task_root/build/power-key/"
sha256sum "$task_root/build/power-key/tzx_power_key.ko"
