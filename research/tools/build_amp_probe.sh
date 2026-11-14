#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-amp-probe-module"
mkdir -p "$out" "$task_root/build/audio-amp-probe"
cp "$task_root/firmware/tzx_amp_probe.c" "$out/"
printf 'obj-m := tzx_amp_probe.o\n' > "$out/Makefile"
make -C "$base/linux-7.3.3" O="$base/kernel-peripheral-build" M="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_amp_probe.ko" "$task_root/build/audio-amp-probe/"
sha256sum "$out/tzx_amp_probe.ko"
