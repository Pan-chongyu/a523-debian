#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
port="$base/aic8800-port"
if test ! -d "$port"; then
    cp -a "$base/avaota-linux/bsp/drivers/net/wireless/aic8800" "$port"
fi
python3 "$task_root/tools/port_aic_7.py"
make -C "$base/linux-7.3.3" O="$base/kernel-build" \
    M="$port/aic8800_bsp" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    CONFIG_PLATFORM_ALLWINNER=n CONFIG_AW_BSP=n CONFIG_AIC_INTF_SDIO=y -j8 modules
make -C "$base/linux-7.3.3" O="$base/kernel-build" \
    M="$port/aic8800_fdrv" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    KBUILD_EXTRA_SYMBOLS="$port/aic8800_bsp/Module.symvers" \
    CONFIG_AIC8800_WLAN_SUPPORT=m CONFIG_PLATFORM_ALLWINNER=n \
    CONFIG_AW_BSP=n CONFIG_GKI_OPT_FEATURES=n CONFIG_AIC_INTF_SDIO=y -j8 modules
mkdir -p "$task_root/build/aic-modules"
cp "$port/aic8800_bsp/aic8800_bsp.ko" "$port/aic8800_fdrv/aic8800_fdrv.ko" "$task_root/build/aic-modules/"
