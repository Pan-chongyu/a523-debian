#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
kernel_src=/opt/a523-debian-20261109/linux-7.3.3
kernel_out=/opt/a523-debian-20261109/kernel-build
mkdir -p "$kernel_out"
cp "$task_root/firmware/sun55i-a523-tzx-p30.dts" "$kernel_src/arch/arm64/boot/dts/allwinner/"
make -C "$kernel_src" O="$kernel_out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    KCONFIG_ALLCONFIG="$task_root/firmware/kernel.config" allnoconfig
make -C "$kernel_src" O="$kernel_out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    -j12 Image modules allwinner/sun55i-a523-tzx-p30.dtb
make -C "$kernel_src" O="$kernel_out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    INSTALL_MOD_PATH="$task_root/build/kernel-modules" modules_install
cp "$kernel_out/arch/arm64/boot/Image" "$task_root/build/Image"
cp "$kernel_out/arch/arm64/boot/dts/allwinner/sun55i-a523-tzx-p30.dtb" "$task_root/build/board.dtb"
cp "$kernel_out/.config" "$task_root/build/kernel.config"
