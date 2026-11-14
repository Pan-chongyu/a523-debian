#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-pmic-poweroff"
mkdir -p "$out" "$task_root/build/pmic-poweroff"
cp "$task_root/firmware/tzx_pmic_poweroff.c" "$out/"
printf 'obj-m := tzx_pmic_poweroff.o\n' > "$out/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-cpufreq-framework-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_pmic_poweroff.ko" "$task_root/build/pmic-poweroff/"
sha256sum "$task_root/build/pmic-poweroff/tzx_pmic_poweroff.ko"
