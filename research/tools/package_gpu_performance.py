"""Package the independently removable GPU clock service."""
import hashlib
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
out = root/'build/gpu-performance'
sources = {
    '/usr/local/lib/tzx-gpu-performance/tzx_gpu_performance.ko': out/'tzx_gpu_performance.ko',
    '/usr/local/lib/tzx-gpu-performance/runtime.py': root/'firmware/tzx_gpu_performance_runtime.py',
    '/usr/local/lib/tzx-gpu-performance/cleanup.py': root/'firmware/tzx_gpu_performance_cleanup.py',
    '/etc/systemd/system/tzx-gpu-performance.service': root/'firmware/tzx-gpu-performance.service',
}
manifest = {'profile': 'fixed-parent-900mV-200-600MHz',
            'files': {p: hashlib.sha256(s.read_bytes()).hexdigest() for p, s in sources.items()}}
(out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
with tarfile.open(out/'runtime.tar.gz', 'w:gz') as archive:
    for name, source in sources.items():
        archive.add(source, arcname=name.lstrip('/'))
    archive.add(out/'manifest.json', arcname='usr/local/lib/tzx-gpu-performance/manifest.json')
print(json.dumps(manifest, indent=2))
