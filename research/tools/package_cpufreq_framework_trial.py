"""Create a hash-pinned manual CPUfreq trial directory for the tablet."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
stage = root / 'build/cpufreq-divider-stage'
stage.mkdir(parents=True, exist_ok=True)
sources = {
    'tzx_cpufreq_divider.ko': root / 'build/cpufreq-divider-v2/tzx_cpufreq_divider.ko',
    'cpu-frequency-workload': root / 'build/cpufreq-framework-kernel/cpu-frequency-workload',
    'memory-check-bounded': root / 'build/memory-check-bounded',
    'run_cpufreq_divider_trial.py': root / 'firmware/run_cpufreq_divider_trial.py',
    'cleanup_cpufreq_divider.py': root / 'firmware/cleanup_cpufreq_divider.py',
}
expected = {
    'tzx_cpufreq_divider.ko': '95a0d572d6a363b1b70984cf51e2ae6dff7e8470fc3a2e66072af5a8a508903c',
    'cpu-frequency-workload': '78ad0fd992c8bd9229a5ff7adf59c4d9eb5fff47d8a79e11644e32300985a7df',
    'memory-check-bounded': '2f7ea0da43c78531b035dc330c8ef51d9764155e21d592679850b8ba0087f4f5',
}
manifest = {}
for name, source in sources.items():
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert name not in expected or digest == expected[name]
    target = stage / name
    target.write_bytes(data)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    manifest[name] = digest
(stage / 'FILES.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'stage': str(stage), 'files': manifest}, indent=2))
