#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
kernel_out="$base/kernel-gpu-clockfix-build"
variant=${1:-shadowfix}
case "$variant" in shadowfix|primefix) ;; *) exit 2 ;; esac
artifact_out="$task_root/build/drm-$variant"
module_out="$base/tzx-drm-$variant-module"
mkdir -p "$module_out" "$artifact_out"
cp "$task_root/firmware/tzx_drm.c" "$task_root/firmware/tzx_de_scanout.c" \
    "$task_root/firmware/tzx_dsi_probe.c" "$task_root/firmware/tzx_dsi_phy.h" \
    "$task_root/firmware/tzx_dsi_video.h" "$module_out/"
printf '#define TZX_PANEL_COMPONENT\n#include "tzx_dsi_probe.c"\n' > "$module_out/tzx_panel_link.c"
printf 'obj-m := tzx_display.o\ntzx_display-y := tzx_drm.o tzx_panel_link.o\n' > "$module_out/Makefile"
make -C "$base/linux-7.3.3" O="$kernel_out" M="$module_out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j8 modules
cp "$module_out/tzx_display.ko" "$artifact_out/"
sha256sum "$artifact_out/tzx_display.ko"
