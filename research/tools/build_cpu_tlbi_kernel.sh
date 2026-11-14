#!/bin/sh
# Isolate the upstream A55 2441007 workaround; retain the #3 clock model.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-7.3.3"
before="$base/kernel-gpu-clockfix-build"
out="$base/kernel-cpu-tlbi-build"
artifacts="$task_root/build/cpu-tlbi-kernel"
mkdir -p "$out" "$artifacts"
if [ ! -f "$out/.config" ]; then
    cp -a --reflink=auto "$before/." "$out/"
fi
"$source/scripts/config" --file "$out/.config" --enable ARM64_ERRATUM_2441007
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
diff -u "$before/.config" "$out/.config" > "$artifacts/config.diff" || test "$?" = 1
python3 - "$before/.config" "$out/.config" <<'PY'
import sys
from pathlib import Path
def settings(path):
    result = {}
    for line in Path(path).read_text().splitlines():
        if line.startswith('CONFIG_'):
            key, value = line.split('=', 1)
            result[key] = value
        elif line.startswith('# CONFIG_'):
            result[line.split()[1]] = 'n'
    return result
a,b=map(settings,sys.argv[1:])
changes={k:(a.get(k),b.get(k)) for k in a.keys()|b.keys() if a.get(k)!=b.get(k)}
assert changes == {'CONFIG_ARM64_ERRATUM_2441007': ('n','y'),
                   'CONFIG_ARM64_WORKAROUND_REPEAT_TLBI_SYNC': (None,'y')}, changes
print('ONLY_A55_2441007_AND_SELECTED_TLBI_SYNC_CHANGED', changes)
PY
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    KBUILD_BUILD_VERSION=4 -j12 Image modules
cp "$out/arch/arm64/boot/Image" "$artifacts/"
cp "$out/.config" "$artifacts/kernel.config"
cp "$out/System.map" "$out/Module.symvers" "$artifacts/"
cmp "$before/arch/arm64/include/generated/asm/cpucap-defs.h" \
    "$out/arch/arm64/include/generated/asm/cpucap-defs.h"
python3 - "$before/Module.symvers" "$out/Module.symvers" <<'PY'
import sys
from pathlib import Path
def entries(path):
    return {r.split()[1]:r.split()[0] for r in Path(path).read_text().splitlines()}
a,b=map(entries,sys.argv[1:])
changed={k:(v,b.get(k)) for k,v in a.items() if b.get(k)!=v}
assert not changed, changed
print('EXISTING_EXPORTED_SYMBOL_CRCS_UNCHANGED',len(a),'new',sorted(b.keys()-a.keys()))
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
