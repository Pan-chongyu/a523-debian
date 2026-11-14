#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-screen-complete"
mkdir -p "$out"
cp "$task_root/build/screen-complete/source/"* "$out/"
printf '#define TZX_PANEL_COMPONENT\n#include "tzx_dsi_probe.c"\n' > "$out/tzx_panel_link.c"
printf 'obj-m := tzx_display.o\ntzx_display-y := tzx_drm.o tzx_panel_link.o\n' > "$out/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-cpufreq-framework-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_display.ko" "$task_root/build/screen-complete/"
sha256sum "$task_root/build/screen-complete/tzx_display.ko"
