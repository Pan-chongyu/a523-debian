#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-bt-runtime"
mkdir -p "$out"
cp "$task_root/firmware/tzx_bt_runtime.c" "$out/"
printf 'obj-m := tzx_bt_runtime.o\n' > "$out/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-peripheral-build" M="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_bt_runtime.ko" "$task_root/build/peripheral-kernel/"
