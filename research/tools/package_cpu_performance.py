"""Package the optional CPU driver and its dedicated thermal policy."""
import hashlib
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
out = root/'build/cpu-performance'
sources = {
    '/usr/local/lib/tzx-cpu-performance/tzx_cpufreq_safepll.ko': out/'tzx_cpufreq_safepll.ko',
    '/usr/local/lib/tzx-cpu-performance/tzx_cpu_perf_cooling.ko': out/'tzx_cpu_perf_cooling.ko',
    '/usr/local/lib/tzx-cpu-performance/runtime.py': root/'firmware/tzx_cpu_performance_runtime.py',
    '/etc/systemd/system/tzx-cpu-performance.service': root/'firmware/tzx-cpu-performance.service',
}
manifest = {'profile': 'fixed-900mV-little792-big1008',
            'files': {p: hashlib.sha256(s.read_bytes()).hexdigest() for p, s in sources.items()}}
(out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
with tarfile.open(out/'runtime.tar.gz', 'w:gz') as archive:
    for name, source in sources.items():
        archive.add(source, arcname=name.lstrip('/'))
    archive.add(out/'manifest.json', arcname='usr/local/lib/tzx-cpu-performance/manifest.json')
print(json.dumps(manifest, indent=2))
