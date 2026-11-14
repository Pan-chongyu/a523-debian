#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
mkdir -p "$base/tzx-touch-module"
cp "$task_root/firmware/tzx_gsl3670.c" "$base/tzx-touch-module/"
cp "$task_root/firmware/tzx_touch_runtime.c" "$base/tzx-touch-module/"
printf 'obj-m := tzx_gsl3670.o tzx_touch_runtime.o\n' > "$base/tzx-touch-module/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-build" M="$base/tzx-touch-module" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j8 modules
cp "$base/tzx-touch-module/tzx_gsl3670.ko" "$task_root/build/"
cp "$base/tzx-touch-module/tzx_touch_runtime.ko" "$task_root/build/"
