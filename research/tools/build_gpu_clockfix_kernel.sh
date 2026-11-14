#!/bin/sh
# Keep the installed accel1 module ABI; change only the built-in GPU clock model.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-7.3.3"
old_out="$base/kernel-acceleration-build"
out="$base/kernel-gpu-clockfix-build"
artifacts="$task_root/build/gpu-clockfix-kernel"
mkdir -p "$out" "$artifacts/source-before"
if [ ! -f "$out/.config" ]; then
    cp -a --reflink=auto "$old_out/." "$out/"
fi
if [ ! -f "$source/drivers/clk/sunxi-ng/ccu_maskdiv.c" ]; then
    for name in Makefile ccu_common.h ccu_mux.c ccu-sun55i-a523.c; do
        cp "$source/drivers/clk/sunxi-ng/$name" "$artifacts/source-before/"
    done
    for number in 0077 0095 0096; do
        set -- "$task_root/upstream/orangepi-reference/$number"-*.patch
        test "$#" = 1
        patch --dry-run --batch -d "$source" -p1 < "$1"
        patch --batch -d "$source" -p1 < "$1"
    done
fi
cmp "$old_out/.config" "$out/.config"
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    KBUILD_BUILD_VERSION=3 -j12 Image modules
cp "$out/arch/arm64/boot/Image" "$artifacts/"
cp "$out/.config" "$artifacts/kernel.config"
cp "$out/System.map" "$artifacts/"
cp "$out/Module.symvers" "$artifacts/"
python3 - "$old_out/Module.symvers" "$out/Module.symvers" <<'PY'
import json,sys
from pathlib import Path
def entries(path):
    return {row.split()[1]: row.split()[0] for row in Path(path).read_text().splitlines()}
before,after=map(entries,sys.argv[1:])
changed={k:[v,after.get(k)] for k,v in before.items() if after.get(k)!=v}
assert not changed, changed
print('EXISTING_EXPORTED_SYMBOL_CRCS_UNCHANGED',len(before),'new',sorted(set(after)-set(before)))
PY
image_bytes=$(stat -c '%s' "$artifacts/Image")
copy_bytes=$(( (image_bytes + 511) / 512 * 512 ))
test "$copy_bytes" -lt 33030144
aarch64-linux-gnu-gcc -static -fno-pie -no-pie -nostdlib -nostartfiles \
    -DTZX_ALIGNED_KERNEL -DTZX_IMAGE_COPY_BYTES=$copy_bytes \
    -Wl,-Ttext=0x4a000000 -Wl,--build-id=none \
    -o "$artifacts/linux-entry.elf" "$task_root/firmware/linux_entry.S"
aarch64-linux-gnu-objcopy -O binary "$artifacts/linux-entry.elf" "$artifacts/linux-entry.bin"
aarch64-linux-gnu-objdump -d "$artifacts/linux-entry.elf" > "$artifacts/linux-entry.disassembly"
sha256sum "$artifacts/Image" "$artifacts/kernel.config" "$artifacts/linux-entry.bin"
