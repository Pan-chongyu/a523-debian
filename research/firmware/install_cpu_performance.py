"""Install this tablet's qualified fixed-voltage CPU performance stack."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert len(sys.argv) == 2 and sys.argv[1] in ('install', 'restore')
root = Path('/usr/local/lib/tzx-cpu-performance')
state_path = Path('/var/lib/tzx/cpu-performance-installed.json')
qualified = Path('/var/lib/tzx/cpu-performance-qualified.json')
unit = 'tzx-cpu-performance.service'

def run(*args):
    subprocess.run(args, check=True, timeout=80)

if sys.argv[1] == 'restore':
    state = json.loads(state_path.read_text())
    run('systemctl', 'disable', '--now', unit)
    assert not Path('/sys/module/tzx_cpufreq_safepll').exists()
    assert not Path('/sys/module/tzx_cpu_perf_cooling').exists()
    # ExecStopPost queues these units to avoid an ordering deadlock. This
    # installer runs outside the stopping unit and can wait for them safely.
    run('systemctl', 'start', 'tzx-cpufreq.service', 'tzx-cpu-cooling.service')
    run('systemctl', 'is-active', 'tzx-cpufreq.service', 'tzx-cpu-cooling.service')
    qualified.unlink(missing_ok=True)
    for name, digest in state['manifest']['files'].items():
        p = Path(name)
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest, name
        p.unlink()
    (root/'manifest.json').unlink()
    if not any(root.iterdir()):
        root.rmdir()
    run('systemctl', 'daemon-reload')
    state['state'] = 'restored-baseline-480MHz'
    state_path.write_text(json.dumps(state, indent=2)+'\n')
    print('CPU_PERFORMANCE_REMOVED_ORIGINAL_480_MHZ_AND_COOLING_RESTORED')
    raise SystemExit(0)

assert not root.exists() and not state_path.exists()
assert not Path('/sys/module/tzx_cpufreq_safepll').exists()
assert not (Path('/etc/systemd/system')/unit).exists()
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
trial = json.loads(Path('/home/debian/cpu-performance/trial-result.json').read_text())
assert trial['status'] == 'PASS' and trial['baseline_restored'] and trial['boot_id'] == boot
assert trial['clock_transitions'] == 160 and trial['eight_core_checksums'] == 40
assert trial['memory_512MiB_passes'] == 3 and trial['thermal_qos_240MHz'] == 'PASS'
assert trial['DSU_backup_PLL_gates_unchanged']
for cpu, khz, improvement in ((0, 792000, 1.5), (4, 1008000, 1.9)):
    baseline = next(r for r in trial['records'] if r['stage'] == 'baseline' and r['cpu'] == cpu)
    faster = next(r for r in trial['records'] if r['stage'] == 'new-driver' and r['cpu'] == cpu and r['khz'] == khz)
    assert baseline['median_thread_seconds']/faster['median_thread_seconds'] > improvement
with tarfile.open('/home/debian/cpu-performance-runtime.tar.gz') as archive:
    members = archive.getmembers()
    expected = {'usr/local/lib/tzx-cpu-performance/tzx_cpufreq_safepll.ko',
                'usr/local/lib/tzx-cpu-performance/tzx_cpu_perf_cooling.ko',
                'usr/local/lib/tzx-cpu-performance/runtime.py',
                'usr/local/lib/tzx-cpu-performance/manifest.json',
                'etc/systemd/system/tzx-cpu-performance.service'}
    assert {m.name for m in members} == expected
    assert all(m.isfile() and '..' not in Path(m.name).parts for m in members)
    for member in members:
        target = Path('/')/member.name
        assert not target.exists() and not target.is_symlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.extractfile(member).read())
        target.chmod(0o644)
manifest = json.loads((root/'manifest.json').read_text())
for name, digest in manifest['files'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
assert manifest['files'][str(root/'tzx_cpufreq_safepll.ko')] == '3c649c8516001f6ea53ee9a86249127e8b2841b288e95dc8f109bff71e87d4ea'
assert manifest['files'][str(root/'tzx_cpu_perf_cooling.ko')] == '26eca91311f4349fd97340429faaf225a8cfbf36cd6f5ac17fce6b777cbc5d0f'
qualified.write_text(json.dumps({'profile': manifest['profile'], 'trial': trial,
                               'scope': 'online tests passed; next physical boot not yet observed'}, indent=2)+'\n')
state = {'manifest': manifest, 'installed_boot_id': boot, 'state': 'installed-online-qualified',
         'boot_areas_changed': False, 'screen_session_restarted': False}
state_path.write_text(json.dumps(state, indent=2)+'\n')
run('systemctl', 'daemon-reload')
run('systemctl', 'enable', '--now', unit)
status = Path('/run/tzx-cpu-performance.json')
for attempt in range(100):
    if status.exists():
        observed = json.loads(status.read_text())
        if observed['boot_id'] == boot and observed['state'] == 'active':
            break
    assert subprocess.run(['systemctl', 'is-active', '--quiet', unit]).returncode == 0
    time.sleep(0.5)
else:
    raise RuntimeError('CPU performance startup did not become ready')
print('CPU_PERFORMANCE_792_1008_MHZ_WITH_STANDARD_THERMAL_QOS_INSTALLED', json.dumps(observed))
