#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
kernel_src="$base/linux-7.3.3"
kernel_out="$base/kernel-graphics-build"
artifact_out="$task_root/build/graphics-kernel"
mkdir -p "$kernel_out" "$artifact_out"
python3 "$task_root/tools/prepare_graphics_kernel.py"
if [ ! -f "$kernel_out/.config" ]; then
    cp "$base/kernel-build/.config" "$kernel_out/.config"
fi
"$kernel_src/scripts/config" --file "$kernel_out/.config" \
    --set-str LOCALVERSION '-tzx-a523-gfx1' \
    -e DRM -m DRM_TZX_A523 -e DRM_KMS_HELPER -e DRM_GEM_SHMEM_HELPER \
    -e DRM_GEM_DMA_HELPER -e DRM_CLIENT_SELECTION -e DRM_FBDEV_EMULATION \
    -e FB -e FRAMEBUFFER_CONSOLE -e FRAMEBUFFER_CONSOLE_DETECT_PRIMARY \
    -e FONT_8x16 -e FONT_16x32 -e INPUT_EVDEV -e UNIX \
    -d DRM_PANIC -d DRM_SIMPLEDRM -d PM
make -C "$kernel_src" O="$kernel_out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
make -C "$kernel_src" O="$kernel_out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j12 Image modules
cp "$kernel_out/arch/arm64/boot/Image" "$artifact_out/Image"
cp "$kernel_out/.config" "$artifact_out/kernel.config"
cp "$kernel_out/System.map" "$artifact_out/System.map"
make -C "$kernel_src" O="$kernel_out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    INSTALL_MOD_PATH="$artifact_out/modules" modules_install
sha256sum "$artifact_out/Image" "$artifact_out/kernel.config"
