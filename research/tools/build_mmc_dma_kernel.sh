#!/bin/sh
# Isolate source and build trees; retain the existing ABI and full RAM.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
original="$base/linux-7.3.3"
source="$base/linux-mmc-dma-source"
before="$base/kernel-cpufreq-framework-build"
out="$base/kernel-mmc-dma-build"
artifacts="$task_root/build/mmc-dma-kernel"
test ! -e "$source"
test ! -e "$out"
mkdir -p "$artifacts"
cp -a --reflink=auto "$original" "$source"
cp -a --reflink=auto "$before" "$out"
python3 "$task_root/tools/prepare_mmc_dma_source.py" "$task_root" "$source"
cmp "$out/.config" "$before/.config"
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    KBUILD_BUILD_VERSION=8 -j12 Image modules
cmp "$out/.config" "$before/.config"
cp "$out/arch/arm64/boot/Image" "$artifacts/"
cp "$out/.config" "$artifacts/kernel.config"
cp "$out/System.map" "$out/Module.symvers" "$artifacts/"
cmp "$before/arch/arm64/include/generated/asm/cpucap-defs.h" \
    "$out/arch/arm64/include/generated/asm/cpucap-defs.h"
image_bytes=$(stat -c '%s' "$artifacts/Image")
copy_bytes=$(( (image_bytes + 511) / 512 * 512 ))
test "$copy_bytes" -lt 33030144
aarch64-linux-gnu-gcc -static -fno-pie -no-pie -nostdlib -nostartfiles \
    -DTZX_ALIGNED_KERNEL -DTZX_IMAGE_COPY_BYTES=$copy_bytes \
    -Wl,-Ttext=0x4a000000 -Wl,--build-id=none \
    -o "$artifacts/linux-entry.elf" "$task_root/firmware/linux_entry.S"
aarch64-linux-gnu-objcopy -O binary "$artifacts/linux-entry.elf" "$artifacts/linux-entry.bin"
python3 - "$artifacts" "$before" "$out" "$original" <<'PY'
import hashlib,json,sys
from pathlib import Path
root,before,out,original=map(Path,sys.argv[1:])
assert (root/'kernel.config').read_bytes()==(before/'.config').read_bytes()
def symbols(path):
    return {row.split()[1]:row.split()[0] for row in path.read_text().splitlines()}
a,b=symbols(before/'Module.symvers'),symbols(out/'Module.symvers')
changes={name:(crc,b.get(name)) for name,crc in a.items() if b.get(name)!=crc}
assert not changes and a.keys()==b.keys(), changes
assert (original/'drivers/mmc/host/sunxi-mmc.c').read_bytes()==(root/'sunxi-mmc-before.c').read_bytes()
record={'release':'7.3.3-tzx-a523-accel1','kernel_build':8,'hardware_tested':False,
    'configuration_unchanged':True,'original_source_unchanged':True,
    'existing_symbols':len(a),'changed_symbol_crcs':changes,
    'external_modules_ABI_unchanged':True,
    'files':{name:hashlib.sha256((root/name).read_bytes()).hexdigest()
        for name in ('Image','kernel.config','linux-entry.bin','Module.symvers','System.map')}}
(root/'BUILD_COMPLETE.json').write_text(json.dumps(record,indent=2)+'\n')
print('MMC_DMA_KERNEL_BUILT_ABI_PASS',json.dumps(record),flush=True)
PY
