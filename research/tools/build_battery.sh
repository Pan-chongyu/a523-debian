#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
for variant in base graphics peripheral; do
    case "$variant" in
    base) out="$base/kernel-build" ;;
    graphics) out="$base/kernel-graphics-build" ;;
    peripheral) out="$base/kernel-peripheral-build" ;;
    esac
    module_out="$base/tzx-battery-$variant"
    mkdir -p "$module_out" "$task_root/build/battery-$variant"
    cp "$task_root/firmware/tzx_battery.c" "$module_out/"
    printf 'obj-m := tzx_battery.o\n' > "$module_out/Makefile"
    make -C "$base/linux-7.3.3" O="$out" M="$module_out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
    cp "$module_out/tzx_battery.ko" "$task_root/build/battery-$variant/"
done
