#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-hs-source"
out="$base/kernel-hs-build"
artifacts="$task_root/build/cpu-gpu-kernel"
mkdir -p "$artifacts"
# Preserve the installed HS build artifacts in build/hs-kernel. The new build
# changes scheduler/cooling integration, not the MMC or trained DRAM paths.
python3 - "$source/drivers/base/arch_topology.c" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]);s=p.read_text()
needle='static u32 *raw_capacity;'
if 'tzx_topology_refresh_capacity' not in s:
    assert s.count(needle)==1
    s=s.replace(needle,'''/* Board driver replaces the conservative early cpufreq policy online.
 * cpu_scale is already exported by topology.c. Queue the existing topology
 * worker after its capacities change; never rebuild under cpufreq locks. */
void tzx_topology_refresh_capacity(void)
{
    schedule_work(&update_topology_flags_work);
}
EXPORT_SYMBOL_GPL(tzx_topology_refresh_capacity);

'''+needle)
    p.write_text(s)
PY
"$source/scripts/config" --file "$out/.config" --enable SCHED_MC --enable DEVFREQ_THERMAL
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig > "$artifacts/config.log" 2>&1
make -C "$source" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- KBUILD_BUILD_VERSION=5 -j8 Image modules > "$artifacts/build.log" 2>&1 || {
    tail -85 "$artifacts/build.log"
    exit 1
}
cp "$out/arch/arm64/boot/Image" "$artifacts/"
cp "$out/.config" "$artifacts/kernel.config"
cp "$out/Module.symvers" "$artifacts/"
cp "$out/drivers/gpu/drm/panfrost/panfrost.ko" "$artifacts/"
image_bytes=$(stat -c '%s' "$artifacts/Image")
copy_bytes=$(( (image_bytes + 511) / 512 * 512 ))
aarch64-linux-gnu-gcc -static -fno-pie -no-pie -nostdlib -nostartfiles \
    -DTZX_ALIGNED_KERNEL -DTZX_IMAGE_COPY_BYTES=$copy_bytes \
    -Wl,-Ttext=0x4a000000 -Wl,--build-id=none \
    -o "$artifacts/linux-entry.elf" "$task_root/firmware/linux_entry.S"
aarch64-linux-gnu-objcopy -O binary "$artifacts/linux-entry.elf" "$artifacts/linux-entry.bin"
sha256sum "$artifacts/Image" "$artifacts/kernel.config" "$artifacts/panfrost.ko"
