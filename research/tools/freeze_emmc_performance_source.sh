#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python3 - "$task_root" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
kernel = Path('/opt/a523-debian-20261109/linux-7.3.3')
build = Path('/opt/a523-debian-20261109/kernel-screen-boot-build')
out = root/'build/emmc-performance/source'
out.mkdir(parents=True,exist_ok=True)
files = {
    'tzx_emmc_performance.c':root/'firmware/tzx_emmc_performance.c',
    'kernel-mmc-core.c':kernel/'drivers/mmc/core/core.c',
    'kernel-mmc-debugfs.c':kernel/'drivers/mmc/core/debugfs.c',
    'kernel-sunxi-mmc.c':kernel/'drivers/mmc/host/sunxi-mmc.c',
    'kernel-mmc-host.h':kernel/'include/linux/mmc/host.h',
    'kernel-mmc-card.h':kernel/'include/linux/mmc/card.h',
    'kernel.config':build/'.config', 'Module.symvers':build/'Module.symvers'}
manifest = {}
for name,source in files.items():
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    (out/name).write_bytes(data)
    manifest[name] = {'source':str(source),'sha256':digest}
(out/'SOURCES.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('EMMC_MATCHING_KERNEL_SOURCES_FROZEN',len(files))
PY
