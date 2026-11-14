"""Freeze the three owned files of the qualified conservative CPUfreq service."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
stage = root / 'build/cpufreq-runtime'
sources = {
    'usr/local/lib/tzx-cpufreq/tzx_cpufreq_divider.ko': root / 'build/cpufreq-divider-v2/tzx_cpufreq_divider.ko',
    'usr/local/lib/tzx-cpufreq/runtime.py': root / 'firmware/tzx_cpufreq_runtime.py',
    'etc/systemd/system/tzx-cpufreq.service': root / 'firmware/tzx-cpufreq.service',
}
manifest = {}
for name, path in sources.items():
    target = stage / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(path.read_bytes())
    manifest[name] = hashlib.sha256(target.read_bytes()).hexdigest()
assert manifest['usr/local/lib/tzx-cpufreq/tzx_cpufreq_divider.ko'] == '95a0d572d6a363b1b70984cf51e2ae6dff7e8470fc3a2e66072af5a8a508903c'
(stage / 'FILES.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
