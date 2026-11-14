#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
module="$base/tzx-native-panfrost"
artifacts="$task_root/build/cpu-gpu-kernel"
python3 - "$task_root" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);s=r/'build/gpu-dma32-aarch64'
assert hashlib.sha256((s/'panfrost-dma32.ko').read_bytes()).hexdigest()=='ad4127adbd990361f89dfa65e3707927609f7eefedc766cd03dedb25f6ba97ae'
for name,digest in json.loads((s/'SOURCE.json').read_text())['files'].items():
    assert hashlib.sha256((s/name.replace('\\','/')).read_bytes()).hexdigest()==digest,name
print('QUALIFIED_DMA32_INITIAL_MMU_AARCH64_SOURCE_VERIFIED')
PY
mkdir -p "$module" "$artifacts/panfrost-source"
cp "$task_root/build/gpu-dma32-aarch64/source/"* "$module/"
cp "$task_root/build/gpu-dma32-aarch64/source/"* "$artifacts/panfrost-source/"
make -C "$base/linux-hs-source" O="$base/kernel-hs-build" M="$module" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$module/panfrost.ko" "$artifacts/"
sha256sum "$artifacts/panfrost.ko"
