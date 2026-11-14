#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-7.3.3"
variant=${1:-graphics}
case "$variant" in
graphics) out="$base/kernel-graphics-build"; artifact_out="$task_root/build/graphics-kernel/peripherals" ;;
peripheral) out="$base/kernel-peripheral-build"; artifact_out="$task_root/build/peripheral-kernel/peripherals" ;;
*) exit 2 ;;
esac
touch_out="$base/tzx-touch-$variant"
wifi_out="$base/tzx-wifi-$variant"
aic_out="$base/radxa-aic8800-$variant"
mkdir -p "$artifact_out" "$touch_out" "$wifi_out"
cp "$task_root/firmware/tzx_gsl3670.c" "$task_root/firmware/tzx_touch_runtime.c" "$touch_out/"
printf 'obj-m := tzx_gsl3670.o tzx_touch_runtime.o\n' > "$touch_out/Makefile"
make -C "$source" O="$out" M="$touch_out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j8 modules
cp "$touch_out/tzx_gsl3670.ko" "$touch_out/tzx_touch_runtime.ko" "$artifact_out/"
cp "$task_root/firmware/tzx_wifi_runtime.c" "$wifi_out/"
printf 'obj-m := tzx_wifi_runtime.o\nccflags-y := -I%s/drivers/mmc/core\n' "$source" > "$wifi_out/Makefile"
make -C "$source" O="$out" M="$wifi_out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j8 modules
cp "$wifi_out/tzx_wifi_runtime.ko" "$artifact_out/"
if [ ! -d "$aic_out" ]; then
    cp -a "$base/radxa-aic8800-port" "$aic_out"
    make -C "$source" O="$out" M="$aic_out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- clean
fi
make -C "$source" O="$out" M="$aic_out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    CONFIG_PLATFORM_ALLWINNER=n CONFIG_PLATFORM_ROCKCHIP=n CONFIG_AIC8800_BTLPM_SUPPORT=n \
    CONFIG_USE_FW_REQUEST=y CONFIG_AIC8800_WLAN_SUPPORT=m CONFIG_AIC_WLAN_SUPPORT=m -j8 modules
cp "$aic_out/aic8800_bsp/aic8800_bsp.ko" "$aic_out/aic8800_fdrv/aic8800_fdrv.ko" "$artifact_out/"
