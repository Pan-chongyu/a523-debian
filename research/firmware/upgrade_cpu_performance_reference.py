"""Refresh schedutil's reference after replacing the early 480 MHz driver."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import time

root = Path('/usr/local/lib/tzx-cpu-performance')
backup = Path('/root/tzx-recovery/cpu-performance-reference')
assert not backup.exists()
old = json.loads((root/'manifest.json').read_text())
for name, digest in old['files'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest
subprocess.run(['systemctl', 'stop', 'tzx-cpu-performance.service'], check=True, timeout=80)
assert not Path('/sys/module/tzx_cpufreq_safepll').exists()
backup.mkdir()
for name in (*old['files'], str(root/'manifest.json'), '/var/lib/tzx/cpu-performance-installed.json'):
    p = Path(name)
    target = backup/p.relative_to('/')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(p.read_bytes())
with tarfile.open('/home/debian/cpu-performance-runtime-v2.tar.gz') as archive:
    members = archive.getmembers()
    expected = {'usr/local/lib/tzx-cpu-performance/'+name for name in
                ('tzx_cpufreq_safepll.ko', 'tzx_cpu_perf_cooling.ko', 'runtime.py', 'manifest.json')}
    expected.add('etc/systemd/system/tzx-cpu-performance.service')
    assert {m.name for m in members} == expected and all(m.isfile() for m in members)
    for member in members:
        target = Path('/')/member.name
        assert not target.is_symlink()
        target.write_bytes(archive.extractfile(member).read())
        target.chmod(0o644)
manifest = json.loads((root/'manifest.json').read_text())
for name, digest in manifest['files'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest
installed_path = Path('/var/lib/tzx/cpu-performance-installed.json')
installed = json.loads(installed_path.read_text())
installed['manifest'] = manifest
installed['reference_frequency'] = 'update exported per-CPU capacity_freq_ref for schedutil, restore on unload'
installed['revision'] = 2
installed_path.write_text(json.dumps(installed, indent=2)+'\n')
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemctl', 'start', 'tzx-cpu-performance.service'], check=True)
for attempt in range(150):
    state = json.loads(Path('/run/tzx-cpu-performance.json').read_text())
    if state['state'] == 'active':
        break
    time.sleep(0.25)
else:
    raise AssertionError('Updated CPU policy did not become ready')
print('CPU_SCHEDUTIL_REFERENCE_UPDATED_FOR_792_1008_MHZ', flush=True)
