"""Preserve the chosen clock while the GPU's normal autosuspend gates it."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import time

root = Path('/usr/local/lib/tzx-gpu-performance')
backup = Path('/root/tzx-recovery/gpu-performance-policy')
assert not backup.exists()
assert json.loads(Path('/home/debian/gpu-performance/trial-result.json').read_text())['status'] == 'PASS'
assert json.loads(Path('/home/debian/gpu-performance/controls-result.json').read_text())['status'] == 'PASS'
old = json.loads((root/'manifest.json').read_text())
for name, digest in old['files'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest
subprocess.run(['systemctl', 'stop', 'tzx-gpu-performance.service'], check=True, timeout=30)
backup.mkdir()
for name in (*old['files'], str(root/'manifest.json'), '/var/lib/tzx/gpu-performance-installed.json'):
    p = Path(name)
    target = backup/p.relative_to('/')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(p.read_bytes())
with tarfile.open('/home/debian/gpu-performance-runtime-v2.tar.gz') as archive:
    members = archive.getmembers()
    expected = {'usr/local/lib/tzx-gpu-performance/'+name for name in
                ('tzx_gpu_performance.ko', 'runtime.py', 'cleanup.py', 'manifest.json')}
    expected.add('etc/systemd/system/tzx-gpu-performance.service')
    assert {m.name for m in members} == expected and all(m.isfile() for m in members)
    for member in members:
        target = Path('/')/member.name
        assert not target.is_symlink()
        target.write_bytes(archive.extractfile(member).read())
        target.chmod(0o644)
manifest = json.loads((root/'manifest.json').read_text())
for name, digest in manifest['files'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest
installed_path = Path('/var/lib/tzx/gpu-performance-installed.json')
installed = json.loads(installed_path.read_text())
installed['manifest'] = manifest
installed['clock_policy'] = 'preserve selected rate through normal runtime clock gating'
installed['process_SIGKILL_recovery'] = 'systemd ExecStopPost returns to 200MHz'
installed_path.write_text(json.dumps(installed, indent=2)+'\n')
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemctl', 'start', 'tzx-gpu-performance.service'], check=True)
for attempt in range(80):
    if Path('/sys/module/tzx_gpu_performance/parameters/active_only').exists():
        if Path('/sys/module/tzx_gpu_performance/parameters/active_only').read_text().strip() == 'N':
            break
    time.sleep(0.25)
else:
    raise AssertionError('GPU policy did not become ready')
assert Path('/sys/bus/platform/devices/1800000.gpu/power/control').read_text().strip() == 'auto'
print('GPU_PERFORMANCE_NO_RESUME_CLOCK_DELAY_NORMAL_AUTOSUSPEND_PRESERVED', flush=True)
