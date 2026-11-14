#!/bin/sh
# Build a separate translation-format comparison; the installed #5 stays intact.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-7.3.3"
before="$base/kernel-cpufreq-framework-build"
out="$base/kernel-48bit-build"
artifacts="$task_root/build/48bit-kernel"
test ! -e "$artifacts/BUILD_COMPLETE.json"
mkdir -p "$artifacts"
if test ! -e "$out"; then cp -a --reflink=auto "$before" "$out"; fi
"$source/scripts/config" --file "$out/.config" \
    --disable ARM64_VA_BITS_52 --enable ARM64_VA_BITS_48 \
    --disable ARM64_PA_BITS_52 --enable ARM64_PA_BITS_48
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
diff -u "$before/.config" "$out/.config" > "$artifacts/config.diff" || test "$?" = 1
python3 - "$before/.config" "$out/.config" <<'PY'
import sys
from pathlib import Path
def values(path):
    result={}
    for row in Path(path).read_text().splitlines():
        if row.startswith('CONFIG_'):
            key,value=row.split('=',1);result[key]=value
        elif row.startswith('# CONFIG_'):
            result[row.split()[1]]='n'
    return result
a,b=map(values,sys.argv[1:])
changes={k:(a.get(k,'n'),b.get(k,'n')) for k in a.keys()|b.keys() if a.get(k,'n')!=b.get(k,'n')}
allowed={'CONFIG_ARM64_VA_BITS_52','CONFIG_ARM64_VA_BITS_48','CONFIG_ARM64_VA_BITS',
         'CONFIG_ARM64_PA_BITS_52','CONFIG_ARM64_PA_BITS_48','CONFIG_ARM64_PA_BITS',
         'CONFIG_ARM64_LPA2','CONFIG_PGTABLE_LEVELS','CONFIG_PGTABLE_RANGE','CONFIG_HAVE_ARCH_HUGE_VMAP'}
assert not changes.keys()-allowed,changes
assert b['CONFIG_ARM64_VA_BITS']=='48' and b['CONFIG_ARM64_PA_BITS']=='48'
print('48BIT_CONFIG_ONLY',changes,flush=True)
PY
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    KBUILD_BUILD_VERSION=7 -j12 Image modules
cp "$out/arch/arm64/boot/Image" "$artifacts/"
cp "$out/.config" "$artifacts/kernel.config"
cp "$out/System.map" "$out/Module.symvers" "$artifacts/"
python3 - "$before/Module.symvers" "$out/Module.symvers" "$artifacts" <<'PY'
import hashlib,json,sys
from pathlib import Path
def symbols(path):
    return {row.split()[1]:row.split()[0] for row in Path(path).read_text().splitlines()}
a,b=map(symbols,sys.argv[1:3]);root=Path(sys.argv[3])
record={'kernel_build':7,'purpose':'48bit VA/PA translation format comparison, full RAM retained',
        'hardware_tested':False,'external_modules_require_rebuild':True,
        'existing_symbols':len(a),'changed':{k:(v,b.get(k)) for k,v in a.items() if b.get(k)!=v},
        'added':sorted(b.keys()-a.keys()),
        'files':{name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                 for name in ('Image','kernel.config','System.map','Module.symvers')}}
(root/'BUILD_COMPLETE.json').write_text(json.dumps(record,indent=2)+'\n')
print('48BIT_BUILD_COMPLETE',json.dumps(record),flush=True)
PY
