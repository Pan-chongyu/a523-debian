#!/bin/sh
# Independent follow-up build; gfx1 and its tested artifacts remain frozen.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-7.3.3"
out="$base/kernel-peripheral-build"
artifacts="$task_root/build/peripheral-kernel"
mkdir -p "$out" "$artifacts"
if [ ! -f "$out/.config" ]; then
    cp "$base/kernel-graphics-build/.config" "$out/.config"
fi
"$source/scripts/config" --file "$out/.config" \
    --set-str LOCALVERSION '-tzx-a523-periph1' \
    -e SOUND -m SND -m SND_SOC -m SND_PCM -m SND_DMAENGINE_PCM \
    -e SND_SOC_GENERIC_DMAENGINE_PCM -e SND_PCM_TIMER \
    -m BT -e BT_BREDR -e BT_LE -m BT_RFCOMM -e BT_RFCOMM_TTY \
    -m BT_BNEP -e BT_BNEP_MC_FILTER -e BT_BNEP_PROTO_FILTER \
    -m BT_HIDP -m BT_HCIUART -e BT_HCIUART_H4 -e BT_HCIUART_SERDEV \
    -e SERIAL_DEV_BUS -e SERIAL_DEV_CTRL_TTYPORT \
    -e OF_DYNAMIC -e OF_OVERLAY -m INPUT_UINPUT -e INPUT_MISC \
    -m INPUT_GPIO_BEEPER -m KEYBOARD_GPIO -e USER_NS -m AUTOFS_FS -d PM
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j12 Image modules
cp "$out/arch/arm64/boot/Image" "$artifacts/"
cp "$out/.config" "$artifacts/kernel.config"
cp "$out/System.map" "$artifacts/"
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    INSTALL_MOD_PATH="$artifacts/modules" modules_install
sha256sum "$artifacts/Image" "$artifacts/kernel.config"
