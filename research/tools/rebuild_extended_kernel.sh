#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-extended-source"
out="$base/kernel-extended-build"
artifacts="$task_root/build/extended-kernel"
port="$base/vpu-reference-port"
test ! -e "$artifacts/VPU_PORT_PREPARED"
for reference in "$task_root"/upstream/performance-reference/0015-*.patch; do
    patch --batch --fuzz=0 -d "$port" -p1 < "$reference"
done
python3 - "$port/drivers/iommu/sun50i-iommu.c" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); text=p.read_text()
assert text.count('.bypass_val = 0x7f & ~BIT(5),') == 1
text=text.replace('.bypass_val = 0x7f & ~BIT(5),', '.bypass_val = 0x7f & ~(BIT(2) | BIT(3)),')
text=text.replace('only the DE\n\t * (master 5, the only one with iommus= in the DTS) is translated. When porting\n\t * the VPU (VE0/VE1 bits 2-3) or DI (bit 6), clear its bit here as well as\n\t * adding iommus= to its node.',
                  'only VPU VE0/VE1 (masters 2-3) are translated.\n\t * TZX scanout uses DMA32 physical addresses: DE master 5 stays bypassed.')
p.write_text(text)
PY
cp "$port/drivers/iommu/sun50i-iommu.c" "$source/drivers/iommu/"
cp "$port/drivers/clk/sunxi-ng/ccu-sun55i-a523.c" "$source/drivers/clk/sunxi-ng/"
cp "$port/include/dt-bindings/reset/sun55i-a523-ccu.h" "$source/include/dt-bindings/reset/"
touch "$artifacts/VPU_PORT_PREPARED"
"$source/scripts/config" --file "$out/.config" --enable BLK_DEV \
    --module ZRAM --enable ZRAM_BACKEND_LZ4 --enable ZRAM_DEF_COMP_LZ4 \
    --disable ZRAM_WRITEBACK --enable SUN50I_IOMMU
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    KBUILD_BUILD_VERSION=5 -j8 Image modules
cp "$out/arch/arm64/boot/Image" "$artifacts/"
cp "$out/.config" "$artifacts/kernel.config"
cp "$out/Module.symvers" "$artifacts/"
image_bytes=$(stat -c '%s' "$artifacts/Image")
copy_bytes=$(( (image_bytes + 511) / 512 * 512 ))
aarch64-linux-gnu-gcc -static -fno-pie -no-pie -nostdlib -nostartfiles \
    -DTZX_ALIGNED_KERNEL -DTZX_IMAGE_COPY_BYTES=$copy_bytes \
    -Wl,-Ttext=0x4a000000 -Wl,--build-id=none \
    -o "$artifacts/linux-entry.elf" "$task_root/firmware/linux_entry.S"
aarch64-linux-gnu-objcopy -O binary "$artifacts/linux-entry.elf" "$artifacts/linux-entry.bin"
sha256sum "$artifacts/Image" "$artifacts/kernel.config"
