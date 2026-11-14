#!/bin/sh
# Recompile board modules against the candidate config and compare machine code.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-extended-source"
out="$base/kernel-extended-build"
workspace="$base/extended-modules"
mkdir -p "$workspace" "$task_root/build/extended-kernel/module-audit"
for relative in tzx-screen-poweron tzx-gpu-dma32-aarch64/panfrost \
    tzx-codec-rates tzx-acceleration-modules tzx-thermal-acceleration \
    tzx-rtc-log tzx-lradc-keys tzx-power-key tzx-pmic-poweroff \
    tzx-display-power tzx-cpu-cooling tzx-cpu-performance tzx-gpu-performance \
    tzx-emmc-performance tzx-cpu-dvfs; do
    destination="$workspace/$relative"
    if [ ! -d "$destination" ]; then
        mkdir -p "$(dirname "$destination")"
        cp -a "$base/$relative" "$destination"
    fi
    make -C "$source" O="$out" M="$destination" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- clean
    # kbuild clean removes generated dtbo blobs. Restore only the source blobs.
    find "$base/$relative" -maxdepth 1 -name '*.dtbo' -exec cp '{}' "$destination/" ';'
    make -C "$source" O="$out" M="$destination" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
    report=$(printf '%s' "$relative" | tr / -)
    python3 "$task_root/tools/audit_extended_module_code.py" "$base/$relative" "$destination" \
      "$task_root/build/extended-kernel/module-audit/$report.json"
done
python3 "$task_root/tools/audit_extended_module_code.py" "$base/kernel-screen-boot-build" "$out" \
    "$task_root/build/extended-kernel/module-audit/kernel-modules.json"
