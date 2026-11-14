#!/bin/sh
# Independent diagnostic build. Preserve the running #5 tree and ABI artifacts.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-7.3.3"
before="$base/kernel-cpufreq-framework-build"
out="$base/kernel-pagecheck-build"
artifacts="$task_root/build/pagecheck-kernel"
test ! -e "$artifacts/BUILD_COMPLETE.json"
mkdir -p "$artifacts"
if test ! -e "$out"; then
    cp -a "$before" "$out"
fi
test -f "$out/.config"
"$source/scripts/config" --file "$out/.config" \
    --enable STRICT_DEVMEM --disable IO_STRICT_DEVMEM \
    --enable PAGE_TABLE_CHECK --enable PAGE_TABLE_CHECK_ENFORCED --enable DEBUG_VM
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
diff -u "$before/.config" "$out/.config" > "$artifacts/config.diff" || test "$?" = 1
python3 - "$before/.config" "$out/.config" <<'PY'
import sys
from pathlib import Path
def settings(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        if line.startswith('CONFIG_'):
            k, v = line.split('=', 1)
            out[k] = v
        elif line.startswith('# CONFIG_'):
            out[line.split()[1]] = 'n'
    return out
a, b = map(settings, sys.argv[1:])
changes = {k: (a.get(k, 'n'), b.get(k, 'n')) for k in a.keys() | b.keys() if a.get(k, 'n') != b.get(k, 'n')}
allowed = {'CONFIG_STRICT_DEVMEM', 'CONFIG_EXCLUSIVE_SYSTEM_RAM', 'CONFIG_PAGE_EXTENSION',
           'CONFIG_PAGE_TABLE_CHECK', 'CONFIG_PAGE_TABLE_CHECK_ENFORCED', 'CONFIG_DEBUG_VM',
           'CONFIG_DEBUG_VM_IRQSOFF'}
assert not (changes.keys() - allowed), changes
assert all(b.get(k) == 'y' for k in allowed), b
print('PAGECHECK_CONFIG_ONLY', changes)
PY
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    KBUILD_BUILD_VERSION=6 -j12 Image modules
cp "$out/arch/arm64/boot/Image" "$artifacts/"
cp "$out/.config" "$artifacts/kernel.config"
cp "$out/System.map" "$out/Module.symvers" "$artifacts/"
cmp "$before/arch/arm64/include/generated/asm/cpucap-defs.h" \
    "$out/arch/arm64/include/generated/asm/cpucap-defs.h"
python3 - "$before/Module.symvers" "$out/Module.symvers" "$artifacts" <<'PY'
import hashlib, json, sys
from pathlib import Path
def entries(path):
    return {line.split()[1]: line.split()[0] for line in Path(path).read_text().splitlines()}
a, b = map(entries, sys.argv[1:3])
changes = {k: (v, b.get(k)) for k, v in a.items() if b.get(k) != v}
root = Path(sys.argv[3])
result = {'kernel_build': 6, 'purpose': 'page table and VM diagnostics only',
          'hardware_tested': False, 'existing_symbols': len(a), 'changed': changes,
          'added': sorted(b.keys() - a.keys()),
          'files': {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                    for name in ('Image', 'kernel.config', 'System.map', 'Module.symvers')}}
(root / 'BUILD_COMPLETE.json').write_text(json.dumps(result, indent=2) + '\n')
print('PAGECHECK_BUILD_COMPLETE', json.dumps(result))
assert not changes
PY
