#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-hs-source";out="$base/kernel-hs-build"
artifacts="$task_root/build/hs-kernel"
mkdir -p "$artifacts"
if [ ! -d "$source" ]; then cp -a "$base/linux-extended-source" "$source"; fi
if [ ! -d "$out" ]; then cp -a "$base/kernel-extended-build" "$out"; fi
python3 "$task_root/tools/prepare_hs_kernel.py"
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- KBUILD_BUILD_VERSION=5 -j8 Image modules
cp "$out/arch/arm64/boot/Image" "$out/.config" "$artifacts/"
mv "$artifacts/.config" "$artifacts/kernel.config"
image_bytes=$(stat -c '%s' "$artifacts/Image")
copy_bytes=$(( (image_bytes + 511) / 512 * 512 ))
aarch64-linux-gnu-gcc -static -fno-pie -no-pie -nostdlib -nostartfiles \
    -DTZX_ALIGNED_KERNEL -DTZX_IMAGE_COPY_BYTES=$copy_bytes \
    -Wl,-Ttext=0x4a000000 -Wl,--build-id=none \
    -o "$artifacts/linux-entry.elf" "$task_root/firmware/linux_entry.S"
aarch64-linux-gnu-objcopy -O binary "$artifacts/linux-entry.elf" "$artifacts/linux-entry.bin"
sha256sum "$artifacts/Image" "$artifacts/kernel.config"
