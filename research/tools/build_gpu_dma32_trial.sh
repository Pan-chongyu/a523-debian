#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
kernel_out="$base/kernel-cpu-tlbi-build"
variant=${1:-gpu-dma32-trial}
case "$variant" in gpu-dma32-trial|gpu-dma32-mmu-init|gpu-dma32-aarch64) ;; *) exit 2 ;; esac
out="$base/tzx-$variant"
artifacts="$task_root/build/$variant"
mkdir -p "$out/panfrost" "$out/display"
cp "$artifacts/source/"* "$out/panfrost/"
make -C "$base/linux-7.3.3" O="$kernel_out" M="$out/panfrost" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j8 modules
cp "$out/panfrost/panfrost.ko" "$artifacts/panfrost-dma32.ko"
cp "$artifacts/display-source/"* "$out/display/"
printf '#define TZX_PANEL_COMPONENT\n#include "tzx_dsi_probe.c"\n' > "$out/display/tzx_panel_link.c"
printf 'obj-m := tzx_display.o\ntzx_display-y := tzx_drm.o tzx_panel_link.o\n' > "$out/display/Makefile"
make -C "$base/linux-7.3.3" O="$kernel_out" M="$out/display" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j8 modules
cp "$out/display/tzx_display.ko" "$artifacts/tzx_display-dma32.ko"
sha256sum "$artifacts/"*.ko
