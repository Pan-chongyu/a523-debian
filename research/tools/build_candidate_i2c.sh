#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-candidate-i2c"
mkdir -p "$out" "$task_root/build/candidate-i2c"
cp "$task_root/firmware/tzx_candidate_i2c.c" "$out/"
printf 'obj-m := tzx_candidate_i2c.o\n' > "$out/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-cpufreq-framework-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_candidate_i2c.ko" "$task_root/build/candidate-i2c/"
sha256sum "$task_root/build/candidate-i2c/tzx_candidate_i2c.ko"
