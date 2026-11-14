"""Repair the stop transaction without restarting the desktop or hardware."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

root = Path('/usr/local/lib/tzx-cpu-performance')
assert not Path('/sys/module/tzx_cpufreq_safepll').exists()
assert hashlib.sha256((root/'tzx_cpufreq_safepll.ko').read_bytes()).hexdigest() == '3c649c8516001f6ea53ee9a86249127e8b2841b288e95dc8f109bff71e87d4ea'
source = Path('/home/debian/tzx_cpu_performance_runtime_v2.py').read_bytes()
assert hashlib.sha256(source).hexdigest() == '0b23acd3dfd2d5f4423a6960993a797815f43ca2f2823fc0e6ca7b4e383e7118'
(root/'runtime.py').write_bytes(source)
manifest = json.loads((root/'manifest.json').read_text())
manifest['files'][str(root/'runtime.py')] = hashlib.sha256(source).hexdigest()
(root/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
state_path = Path('/var/lib/tzx/cpu-performance-installed.json')
state = json.loads(state_path.read_text())
state['manifest'] = manifest
state['stop_transaction'] = 'queue baseline services without blocking ordered stop'
state_path.write_text(json.dumps(state, indent=2)+'\n')
Path('/var/lib/tzx/cpu-performance-pending.json').unlink(missing_ok=True)
subprocess.run(['systemctl', 'start', 'tzx-cpufreq.service', 'tzx-cpu-cooling.service'], check=True, timeout=40)
subprocess.run(['systemctl', 'reset-failed', 'tzx-cpu-performance.service'], check=True)
subprocess.run(['systemctl', 'start', 'tzx-cpu-performance.service'], check=True)
for attempt in range(150):
    state = json.loads(Path('/run/tzx-cpu-performance.json').read_text())
    if state['state'] == 'active':
        break
    time.sleep(0.25)
else:
    raise RuntimeError('CPU performance did not recover')
print('CPU_PERFORMANCE_STOP_TRANSACTION_AND_SCHEDUTIL_REFERENCE_REPAIRED', flush=True)
