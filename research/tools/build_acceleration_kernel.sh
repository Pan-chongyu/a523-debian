#!/bin/sh
# Independent runtime-PM/thermal/Panfrost candidate; never mutate periph1.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-7.3.3"
out="$base/kernel-acceleration-build"
artifacts="$task_root/build/acceleration-kernel"
mkdir -p "$out" "$artifacts"
if [ ! -f "$out/.config" ]; then
    cp "$base/kernel-peripheral-build/.config" "$out/.config"
fi
"$source/scripts/config" --file "$out/.config" \
    --set-str LOCALVERSION '-tzx-a523-accel1' \
    -e PM -d SUSPEND -d HIBERNATION -e PM_DEBUG \
    -e THERMAL -e THERMAL_OF -e HWMON -e THERMAL_HWMON \
    -e NVMEM -e NVMEM_SUNXI_SID \
    -d SUN8I_THERMAL -m DRM_PANFROST -m SUN55I_PCK600 \
    -e MAGIC_SYSRQ -e WATCHDOG -m SUNXI_WATCHDOG
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j12 Image modules
cp "$out/arch/arm64/boot/Image" "$artifacts/"
cp "$out/.config" "$artifacts/kernel.config"
cp "$out/System.map" "$artifacts/"
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    INSTALL_MOD_PATH="$artifacts/modules" modules_install
sha256sum "$artifacts/Image" "$artifacts/kernel.config"
