#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-dsi-irq-probe"
mkdir -p "$out" "$task_root/build/dsi-irq-probe"
cp "$task_root/firmware/tzx_dsi_irq_probe.c" "$out/"
printf 'obj-m := tzx_dsi_irq_probe.o\n' > "$out/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-cpufreq-framework-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_dsi_irq_probe.ko" "$task_root/build/dsi-irq-probe/"
sha256sum "$task_root/build/dsi-irq-probe/tzx_dsi_irq_probe.ko"
