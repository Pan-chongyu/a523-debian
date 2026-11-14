#!/bin/sh
# Add fbcon rotation while keeping the qualified external-module ABI.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-7.3.3"
before="$base/kernel-cpufreq-framework-build"
out="$base/kernel-screen-boot-build"
artifacts="$task_root/build/screen-boot-kernel"
test ! -e "$out"
test ! -e "$artifacts/BUILD_COMPLETE.json"
mkdir -p "$artifacts"
cp -a "$before" "$out"
"$source/scripts/config" --file "$out/.config" --enable FRAMEBUFFER_CONSOLE_ROTATION
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
python3 - "$before/.config" "$out/.config" <<'PY'
import sys
from pathlib import Path
def settings(path):
    return {row.split('=', 1)[0]: row.split('=', 1)[1] for row in Path(path).read_text().splitlines()
            if row.startswith('CONFIG_')}
a, b = map(settings, sys.argv[1:])
changes = {k: (a.get(k, 'n'), b.get(k, 'n')) for k in a.keys() | b.keys() if a.get(k, 'n') != b.get(k, 'n')}
assert changes == {'CONFIG_FRAMEBUFFER_CONSOLE_ROTATION': ('n', 'y')}, changes
print('SCREEN_BOOT_CONFIG_CHANGE', changes)
PY
# Preserve the #5 ABI tag; provenance is recorded separately in BUILD_COMPLETE.
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    KBUILD_BUILD_VERSION=5 -j8 Image modules
cp "$out/arch/arm64/boot/Image" "$artifacts/"
cp "$out/.config" "$artifacts/kernel.config"
cp "$out/Module.symvers" "$artifacts/"
cmp "$before/arch/arm64/include/generated/asm/cpucap-defs.h" "$out/arch/arm64/include/generated/asm/cpucap-defs.h"
python3 - "$before/Module.symvers" "$out/Module.symvers" "$artifacts" <<'PY'
import json, sys
from pathlib import Path
def symbols(path):
    return {line.split()[1]: line.split()[0] for line in Path(path).read_text().splitlines()}
a, b = map(symbols, sys.argv[1:3])
changes = {k: (v, b.get(k)) for k, v in a.items() if b.get(k) != v}
record = {'existing_symbols': len(a), 'changed': changes, 'added': sorted(b.keys() - a.keys()),
          'config_change': 'CONFIG_FRAMEBUFFER_CONSOLE_ROTATION=y', 'hardware_tested': False}
Path(sys.argv[3], 'ABI.json').write_text(json.dumps(record, indent=2)+'\n')
assert not changes, changes
print('SCREEN_BOOT_EXISTING_SYMBOL_ABI_UNCHANGED', len(a))
PY
image_bytes=$(stat -c '%s' "$artifacts/Image")
copy_bytes=$(( (image_bytes + 511) / 512 * 512 ))
test "$copy_bytes" -lt 33030144
aarch64-linux-gnu-gcc -static -fno-pie -no-pie -nostdlib -nostartfiles \
    -DTZX_ALIGNED_KERNEL -DTZX_IMAGE_COPY_BYTES=$copy_bytes \
    -Wl,-Ttext=0x4a000000 -Wl,--build-id=none \
    -o "$artifacts/linux-entry.elf" "$task_root/firmware/linux_entry.S"
aarch64-linux-gnu-objcopy -O binary "$artifacts/linux-entry.elf" "$artifacts/linux-entry.bin"
python3 - "$artifacts" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
(root/'BUILD_COMPLETE.json').write_text(json.dumps({
    'status': 'built_not_hardware_tested', 'kernel_module_abi_tag': 5,
    'config_change': 'CONFIG_FRAMEBUFFER_CONSOLE_ROTATION=y',
    'files': {n: hashlib.sha256((root/n).read_bytes()).hexdigest()
              for n in ('Image', 'kernel.config', 'linux-entry.bin', 'Module.symvers')}
}, indent=2)+'\n')
PY
sha256sum "$artifacts/Image" "$artifacts/kernel.config"
