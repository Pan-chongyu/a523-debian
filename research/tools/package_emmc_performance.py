"""Package the qualified additive eMMC clock service."""
import hashlib
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
out = root/'build/emmc-performance'
files = {
    '/usr/local/lib/tzx-emmc-performance/tzx_emmc_performance.ko':out/'tzx_emmc_performance.ko',
    '/usr/local/lib/tzx-emmc-performance/runtime.py':root/'firmware/tzx_emmc_performance_runtime.py',
    '/usr/local/lib/tzx-emmc-performance/cleanup.py':root/'firmware/tzx_emmc_performance_cleanup.py',
    '/etc/systemd/system/tzx-emmc-performance.service':root/'firmware/tzx-emmc-performance.service'}
manifest = {'profile':'exact-CID-DDR52-50MHz-lease-25MHz-fallback',
            'files':{name:hashlib.sha256(p.read_bytes()).hexdigest() for name,p in files.items()}}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
with tarfile.open(out/'runtime.tar.gz','w:gz') as archive:
    for name,p in files.items():
        archive.add(p,arcname=name.lstrip('/'))
    archive.add(out/'manifest.json',arcname='usr/local/lib/tzx-emmc-performance/manifest.json')
print(json.dumps(manifest,indent=2))
