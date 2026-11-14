#!/bin/sh
# Keep the existing CPU/PLL source and enable only the CPUfreq framework.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-7.3.3"
before="$base/kernel-cpu-tlbi-build"
out="$base/kernel-cpufreq-framework-build"
artifacts="$task_root/build/cpufreq-framework-kernel"
mkdir -p "$out" "$artifacts"
test ! -e "$artifacts/BUILD_COMPLETE.json"
cp "$before/.config" "$out/.config"
"$source/scripts/config" --file "$out/.config" \
    --enable CPU_FREQ --enable CPU_FREQ_STAT \
    --disable CPU_FREQ_DEFAULT_GOV_SCHEDUTIL --enable CPU_FREQ_DEFAULT_GOV_PERFORMANCE \
    --enable CPU_FREQ_GOV_PERFORMANCE --enable CPU_FREQ_GOV_POWERSAVE \
    --enable CPU_FREQ_GOV_USERSPACE --enable CPU_FREQ_GOV_SCHEDUTIL \
    --disable CPU_FREQ_DT --disable ARM_SCPI_CPUFREQ --disable ARM_SCMI_CPUFREQ \
    --disable ARM_ALLWINNER_SUN50I_CPUFREQ_NVMEM
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
diff -u "$before/.config" "$out/.config" > "$artifacts/config.diff" || test "$?" = 1
python3 - "$before/.config" "$out/.config" <<'PY'
import sys
from pathlib import Path
def settings(path):
    values = {}
    for row in Path(path).read_text().splitlines():
        if row.startswith('CONFIG_'):
            name, value = row.split('=', 1)
            values[name] = value
        elif row.startswith('# CONFIG_'):
            values[row.split()[1]] = 'n'
    return values
a, b = map(settings, sys.argv[1:])
changes = {k: (a.get(k, 'n'), b.get(k, 'n'))
           for k in a.keys() | b.keys() if a.get(k, 'n') != b.get(k, 'n')}
assert all(k.startswith(('CONFIG_CPU_FREQ', 'CONFIG_CPUFREQ', 'CONFIG_ARM_', 'CONFIG_ACPI_CPPC_',
                         'CONFIG_DT_IDLE_', 'CONFIG_QORIQ_')) or k == 'CONFIG_IRQ_WORK' for k in changes), changes
assert not any(b.get(k) in ('y', 'm') for k in ('CONFIG_CPU_FREQ_DT', 'CONFIG_ARM_SCPI_CPUFREQ',
    'CONFIG_ARM_SCMI_CPUFREQ', 'CONFIG_ARM_ALLWINNER_SUN50I_CPUFREQ_NVMEM'))
print('CPUFREQ_FRAMEWORK_CONFIG_CHANGES', changes)
PY
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    KBUILD_BUILD_VERSION=5 -j12 Image modules
cp "$out/arch/arm64/boot/Image" "$artifacts/"
cp "$out/.config" "$artifacts/kernel.config"
cp "$out/System.map" "$out/Module.symvers" "$artifacts/"
cmp "$before/arch/arm64/include/generated/asm/cpucap-defs.h" \
    "$out/arch/arm64/include/generated/asm/cpucap-defs.h"
python3 - "$before/Module.symvers" "$out/Module.symvers" "$artifacts" <<'PY'
import hashlib, json, sys
from pathlib import Path
def entries(path):
    return {row.split()[1]: row.split()[0] for row in Path(path).read_text().splitlines()}
a, b = map(entries, sys.argv[1:3])
changes = {name: (crc, b.get(name)) for name, crc in a.items() if b.get(name) != crc}
record = {'existing_symbols': len(a), 'changed': changes, 'added': sorted(b.keys() - a.keys()),
          'purpose': 'CPUfreq core/governors only; no board frequency driver built in',
          'hardware_tested': False}
Path(sys.argv[3], 'ABI.json').write_text(json.dumps(record, indent=2) + '\n')
print('CPUFREQ_EXISTING_SYMBOL_CRC_CHANGES', len(changes))
assert not changes, 'Rebuild the affected external modules before considering a hardware test'
PY
image_bytes=$(stat -c '%s' "$artifacts/Image")
copy_bytes=$(( (image_bytes + 511) / 512 * 512 ))
test "$copy_bytes" -lt 33030144
aarch64-linux-gnu-gcc -static -fno-pie -no-pie -nostdlib -nostartfiles \
    -DTZX_ALIGNED_KERNEL -DTZX_IMAGE_COPY_BYTES=$copy_bytes \
    -Wl,-Ttext=0x4a000000 -Wl,--build-id=none \
    -o "$artifacts/linux-entry.elf" "$task_root/firmware/linux_entry.S"
aarch64-linux-gnu-objcopy -O binary "$artifacts/linux-entry.elf" "$artifacts/linux-entry.bin"
module="$artifacts/divider-module"
mkdir -p "$module"
cp "$task_root/firmware/tzx_cpufreq_divider.c" "$module/"
printf 'obj-m += tzx_cpufreq_divider.o\n' > "$module/Makefile"
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- M="$module" modules
aarch64-linux-gnu-gcc -O2 -static -Wall -Wextra -o "$artifacts/cpu-frequency-workload" \
    "$task_root/firmware/cpu_frequency_workload.c"
python3 - "$artifacts" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
names = ('Image', 'kernel.config', 'linux-entry.bin', 'divider-module/tzx_cpufreq_divider.ko',
         'cpu-frequency-workload')
(root / 'BUILD_COMPLETE.json').write_text(json.dumps({
    'status': 'built_not_hardware_tested', 'kernel_build': 5,
    'cpufreq_board_driver_autostart': False,
    'files': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}
}, indent=2) + '\n')
PY
sha256sum "$artifacts/Image" "$artifacts/divider-module/tzx_cpufreq_divider.ko"
