#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-extended-source"
out="$base/kernel-extended-build"
workspace="$base/extended-modules"
for relative in tzx-gpu-acceleration tzx-bt-runtime tzx-battery-peripheral \
    tzx-rtc-context tzx-touch-peripheral tzx-wifi-performance; do
    destination="$workspace/$relative"
    if [ ! -d "$destination" ]; then cp -a "$base/$relative" "$destination"; fi
    make -C "$source" O="$out" M="$destination" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- clean
    find "$base/$relative" -maxdepth 1 -name '*.dtbo' -exec cp '{}' "$destination/" ';'
    make -C "$source" O="$out" M="$destination" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
done
relative=radxa-aic8800-acceleration
destination="$workspace/$relative"
if [ ! -d "$destination" ]; then cp -a "$base/$relative" "$destination"; fi
make -C "$source" O="$out" M="$destination" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- clean
make -C "$source" O="$out" M="$destination" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    CONFIG_PLATFORM_ALLWINNER=n CONFIG_PLATFORM_ROCKCHIP=n CONFIG_AIC8800_BTLPM_SUPPORT=n \
    CONFIG_USE_FW_REQUEST=y CONFIG_AIC8800_WLAN_SUPPORT=m CONFIG_AIC_WLAN_SUPPORT=m -j8 modules
relative=cpufreq-divider
destination="$workspace/$relative"
if [ ! -d "$destination" ]; then cp -a "$task_root/build/cpufreq-framework-kernel/divider-module" "$destination"; fi
make -C "$source" O="$out" M="$destination" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- clean
make -C "$source" O="$out" M="$destination" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
python3 - "$task_root" <<'PY'
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]+'/tools')
from audit_extended_module_code import compare
root=Path(sys.argv[1]);base=Path('/opt/a523-debian-20261109')
records=[]
for p in (base/'extended-modules').rglob('*.ko'):
    relative=p.relative_to(base/'extended-modules')
    old=base/relative
    if relative.parts[0]=='cpufreq-divider': old=root/'build/cpufreq-framework-kernel/divider-module'/relative.name
    if old.exists(): records.append(compare(old,p))
for p in (base/'kernel-screen-boot-build').rglob('*.ko'):
    candidate=base/'kernel-extended-build'/p.relative_to(base/'kernel-screen-boot-build')
    assert candidate.exists(),p
    records.append(compare(p,candidate))
path=root/'build/extended-kernel/module-audit/complete.json'
path.write_text(json.dumps(records,indent=2)+'\n')
assert len(records)>55,len(records)
active=[r for r in records if not any(s in r['before'] for s in ('/tzx-battery-peripheral/','/tzx-touch-peripheral/','/tzx-bt-runtime/'))]
# Those three obsolete periph1 builds are not the accel1 modules installed on
# the tablet. Their active equivalents are compared in tzx-acceleration-modules.
assert all(r['equal_after_normalizing_source_directory'] for r in active),[r for r in active if not r['equal_after_normalizing_source_directory']]
print('ACTIVE_MODULE_ALLOCATABLE_CODE_AND_DATA_COMPATIBLE',len(active))
PY
