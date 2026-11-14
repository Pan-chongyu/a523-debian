#!/bin/sh
# Isolated swap/video groundwork. Never modify the working kernel build.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-extended-source"
out="$base/kernel-extended-build"
artifacts="$task_root/build/extended-kernel"
test ! -e "$source"
test ! -e "$out"
mkdir -p "$artifacts"
cp -a "$base/linux-7.3.3" "$source"
cp -a "$base/kernel-screen-boot-build" "$out"
# The copied output Makefile points at the original sources; regenerate it.
rm "$out/Makefile"
"$source/scripts/config" --file "$out/.config" --enable SWAP \
    --module ZRAM --enable ZRAM_BACKEND_LZ4 --enable ZRAM_DEF_COMP_LZ4 \
    --disable ZRAM_WRITEBACK --enable DMABUF_HEAPS --module DMABUF_HEAPS_SYSTEM \
    --module SUN50I_IOMMU
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    KBUILD_BUILD_VERSION=5 -j8 Image modules
cp "$out/arch/arm64/boot/Image" "$artifacts/"
cp "$out/.config" "$artifacts/kernel.config"
cp "$out/Module.symvers" "$artifacts/"
image_bytes=$(stat -c '%s' "$artifacts/Image")
copy_bytes=$(( (image_bytes + 511) / 512 * 512 ))
test "$copy_bytes" -lt 14000000
aarch64-linux-gnu-gcc -static -fno-pie -no-pie -nostdlib -nostartfiles \
    -DTZX_ALIGNED_KERNEL -DTZX_IMAGE_COPY_BYTES=$copy_bytes \
    -Wl,-Ttext=0x4a000000 -Wl,--build-id=none \
    -o "$artifacts/linux-entry.elf" "$task_root/firmware/linux_entry.S"
aarch64-linux-gnu-objcopy -O binary "$artifacts/linux-entry.elf" "$artifacts/linux-entry.bin"
sha256sum "$artifacts/Image" "$artifacts/kernel.config"
