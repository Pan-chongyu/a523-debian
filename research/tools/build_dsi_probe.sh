#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
python3 "$task_root/tools/prepare_dsi_reference.py"
mkdir -p "$base/tzx-dsi-module"
cp "$task_root/firmware/tzx_dsi_probe.c" "$task_root/firmware/tzx_dsi_phy.h" \
    "$task_root/firmware/tzx_dsi_video.h" "$base/tzx-dsi-module/"
printf 'obj-m := tzx_dsi_probe.o\n' > "$base/tzx-dsi-module/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-build" M="$base/tzx-dsi-module" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j8 modules
cp "$base/tzx-dsi-module/tzx_dsi_probe.ko" "$task_root/build/"
