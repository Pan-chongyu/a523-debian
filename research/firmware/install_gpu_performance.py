"""Install only after this device's real clock/load/control tests pass."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert len(sys.argv) == 2 and sys.argv[1] in ('install', 'restore')
root = Path('/usr/local/lib/tzx-gpu-performance')
state_path = Path('/var/lib/tzx/gpu-performance-installed.json')
qualified = Path('/var/lib/tzx/gpu-performance-qualified.json')
unit = 'tzx-gpu-performance.service'

def run(*args):
    subprocess.run(args, check=True, timeout=65)

if sys.argv[1] == 'restore':
    state = json.loads(state_path.read_text())
    run('systemctl', 'disable', '--now', unit)
    assert not Path('/sys/module/tzx_gpu_performance').exists()
    assert int(Path('/sys/kernel/debug/clk/gpu/clk_rate').read_text()) == 200000000
    qualified.unlink(missing_ok=True)
    for name, digest in state['manifest']['files'].items():
        p = Path(name)
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest, name
        p.unlink()
    (root/'manifest.json').unlink()
    if not any(root.iterdir()):
        root.rmdir()
    run('systemctl', 'daemon-reload')
    state['state'] = 'restored-baseline-200MHz'
    state_path.write_text(json.dumps(state, indent=2)+'\n')
    print('GPU_PERFORMANCE_REMOVED_BASELINE_200_MHZ')
    raise SystemExit(0)

assert not root.exists() and not state_path.exists()
assert not Path('/sys/module/tzx_gpu_performance').exists()
assert not Path('/etc/systemd/system'/Path(unit)).exists()
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
trial = json.loads(Path('/home/debian/gpu-performance/trial-result.json').read_text())
controls = json.loads(Path('/home/debian/gpu-performance/controls-result.json').read_text())
assert trial['status'] == controls['status'] == 'PASS'
assert trial['boot_id'] == controls['boot_id'] == boot
assert [r['mhz'] for r in trial['records']] == [200, 300, 400, 600, 600]
assert trial['records'][3]['score'] > trial['records'][0]['score'] * 1.5
assert controls['invalid_800_mhz_rejected']
with tarfile.open('/home/debian/gpu-performance-runtime.tar.gz') as archive:
    members = archive.getmembers()
    expected = {'usr/local/lib/tzx-gpu-performance/tzx_gpu_performance.ko',
                'usr/local/lib/tzx-gpu-performance/runtime.py',
                'usr/local/lib/tzx-gpu-performance/cleanup.py',
                'usr/local/lib/tzx-gpu-performance/manifest.json',
                'etc/systemd/system/tzx-gpu-performance.service'}
    assert {m.name for m in members} == expected
    assert all(m.isfile() and '..' not in Path(m.name).parts for m in members)
    for m in members:
        target = Path('/')/m.name
        assert not target.exists() and not target.is_symlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.extractfile(m).read())
        target.chmod(0o644)
manifest = json.loads((root/'manifest.json').read_text())
for name, digest in manifest['files'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
assert manifest['files'][str(root/'tzx_gpu_performance.ko')] == '2f5b336419d723849a68dc0b86c00e04d13eb9bca5cffff19455d060c5989659'
qualification = {'profile': manifest['profile'], 'trial': trial, 'controls': controls,
                 'module_sha256': manifest['files'][str(root/'tzx_gpu_performance.ko')],
                 'scope': 'online tests passed; next physical boot not yet observed'}
qualified.write_text(json.dumps(qualification, indent=2)+'\n')
state = {'manifest': manifest, 'installed_boot_id': boot, 'state': 'installed-online-qualified',
         'boot_areas_changed': False, 'screen_session_restarted': False}
state_path.write_text(json.dumps(state, indent=2)+'\n')
run('systemctl', 'daemon-reload')
run('systemctl', 'enable', '--now', unit)
run('systemctl', 'is-active', unit)
print('GPU_PERFORMANCE_600_MHZ_INSTALLED_WITH_200_MHZ_FALLBACK')
