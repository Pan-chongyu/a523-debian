#!/bin/sh
# Give the address-layout experiment its own module namespace.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-7.3.3"
out="$base/kernel-48bit-build"
original="$task_root/build/48bit-kernel"
artifacts="$task_root/build/va48-kernel"
test -f "$original/BUILD_COMPLETE.json"
test ! -e "$artifacts/BUILD_COMPLETE.json"
mkdir -p "$artifacts"
"$source/scripts/config" --file "$out/.config" --set-str LOCALVERSION '-tzx-a523-va48'
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    KBUILD_BUILD_VERSION=7 -j12 Image modules
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    INSTALL_MOD_PATH="$artifacts/modules" modules_install
cp "$out/arch/arm64/boot/Image" "$artifacts/"
cp "$out/.config" "$artifacts/kernel.config"
cp "$out/System.map" "$out/Module.symvers" "$artifacts/"
image_bytes=$(stat -c '%s' "$artifacts/Image")
copy_bytes=$(( (image_bytes + 511) / 512 * 512 ))
test "$copy_bytes" -lt 33030144
aarch64-linux-gnu-gcc -static -fno-pie -no-pie -nostdlib -nostartfiles \
    -DTZX_ALIGNED_KERNEL -DTZX_IMAGE_COPY_BYTES=$copy_bytes \
    -Wl,-Ttext=0x4a000000 -Wl,--build-id=none \
    -o "$artifacts/linux-entry.elf" "$task_root/firmware/linux_entry.S"
aarch64-linux-gnu-objcopy -O binary "$artifacts/linux-entry.elf" "$artifacts/linux-entry.bin"
module="$artifacts/rtc-module"
mkdir -p "$module"
cp "$task_root/firmware/tzx_rtc_log.c" "$module/"
printf 'obj-m := tzx_rtc_log.o\n' > "$module/Makefile"
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- M="$module" modules
python3 - "$artifacts" "$base/kernel-cpufreq-framework-build" <<'PY'
import hashlib,json,sys
from pathlib import Path
root,before=map(Path,sys.argv[1:])
def values(path):
    output={}
    for row in path.read_text().splitlines():
        if row.startswith('CONFIG_'):
            k,v=row.split('=',1);output[k]=v
        elif row.startswith('# CONFIG_'):output[row.split()[1]]='n'
    return output
a,b=values(before/'.config'),values(root/'kernel.config')
changes={k:(a.get(k,'n'),b.get(k,'n')) for k in a.keys()|b.keys() if a.get(k,'n')!=b.get(k,'n')}
allowed={'CONFIG_ARM64_VA_BITS_52','CONFIG_ARM64_VA_BITS_48','CONFIG_ARM64_VA_BITS',
 'CONFIG_ARM64_PA_BITS_52','CONFIG_ARM64_PA_BITS_48','CONFIG_ARM64_PA_BITS',
 'CONFIG_ARM64_LPA2','CONFIG_PGTABLE_LEVELS','CONFIG_LOCALVERSION'}
assert not changes.keys()-allowed,changes
names=['Image','kernel.config','linux-entry.bin','rtc-module/tzx_rtc_log.ko']
record={'release':'7.3.3-tzx-a523-va48','kernel_build':7,'hardware_tested':False,
        'config_changes':changes,'module_namespace_isolated':True,
        'files':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}}
(root/'BUILD_COMPLETE.json').write_text(json.dumps(record,indent=2)+'\n')
print('VA48_BUILD_COMPLETE',json.dumps(record),flush=True)
PY
