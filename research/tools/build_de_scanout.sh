#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
mkdir -p "$base/tzx-de-module"
cp "$task_root/firmware/tzx_de_scanout.c" "$base/tzx-de-module/"
printf 'obj-m := tzx_de_scanout.o\n' > "$base/tzx-de-module/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-build" M="$base/tzx-de-module" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j8 modules
cp "$base/tzx-de-module/tzx_de_scanout.ko" "$task_root/build/"
