#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/kernel-extended-build"
artifacts="$task_root/build/extended-kernel"
mkdir -p "$artifacts/native"
for relative in mm/zsmalloc.ko lib/lz4/lz4_compress.ko lib/lz4/lz4_decompress.ko drivers/block/zram/zram.ko drivers/dma-buf/heaps/system_heap.ko; do
    test -f "$out/$relative"
    mkdir -p "$artifacts/native/$(dirname "$relative")"
    cp "$out/$relative" "$artifacts/native/$relative"
done
cp "$base/vpu-cedar-port/drivers/media/platform/sunxi/cedar-ve/sunxi-ve.ko" "$artifacts/"
tar -C "$artifacts" -czf "$artifacts/install.tar.gz" linux-bundle.bin linux-bundle.json kernel.config native
sha256sum "$artifacts/install.tar.gz" "$artifacts/sunxi-ve.ko"
