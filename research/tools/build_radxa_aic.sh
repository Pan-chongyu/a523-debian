#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
src="$base/radxa-aic8800/src/SDIO/driver_fw/driver/aic8800"
port="$base/radxa-aic8800-port"
test -f "$src/aic8800_fdrv/Makefile"
mkdir -p "$port"
cp -a "$src/." "$port/"
python3 "$task_root/tools/port_radxa_aic_7.py"
make -C "$base/linux-7.3.3" O="$base/kernel-build" M="$port" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_PLATFORM_ALLWINNER=n \
    CONFIG_PLATFORM_ROCKCHIP=n CONFIG_AIC8800_BTLPM_SUPPORT=n CONFIG_USE_FW_REQUEST=y \
    CONFIG_AIC8800_WLAN_SUPPORT=m CONFIG_AIC_WLAN_SUPPORT=m -j8 modules
mkdir -p "$task_root/build/radxa-aic-modules"
find "$port" -name '*.ko' -exec cp '{}' "$task_root/build/radxa-aic-modules/" \;
