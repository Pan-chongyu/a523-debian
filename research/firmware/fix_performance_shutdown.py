"""Keep normal SIGTERM from killing a supervisor's active diagnostic child."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
sha = lambda b: hashlib.sha256(b).hexdigest()
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
state = Path('/var/lib/tzx')
backup = Path('/root/tzx-recovery/performance-clean-shutdown-v1')
assert not backup.exists() and not (state/'performance-clean-shutdown.json').exists()
failure = json.loads((state/'cpu-full-failure.json').read_text())
assert failure == dict(boot_id='91294d8e-9cab-43b8-9a38-4cab9e1cc2d5',
                      error="CalledProcessError(-15, ('dmesg',))")
proof = (state/'cpu-full-revoked.json').read_bytes()
assert sha(proof) == 'c537a6d4f97b28c938b4dd88e40276d5d161b0c64ef6e234e06eeca7d5f4c368'
assert not (state/'cpu-full-qualified.json').exists() and not (state/'cpu-full-pending.json').exists()
value = json.loads(proof)
assert value['profile'] == 'vf0300-little1416-big1800-native-capacity'
assert value['trial']['status'] == 'PASS' and value['trial']['baseline_restored']
assert value['normal_reboot_verified'] and value['poweroff_key_on_verified']


def run(*args, timeout=85):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=timeout)


def atomic(path, data, mode=0o600):
    assert not path.is_symlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.shutdown-new')
    with temp.open('wb') as f:
        f.write(data)
        os.fchmod(f.fileno(), mode)
        f.flush()
        os.fsync(f.fileno())
    temp.replace(path)


for component in ('tzx-cpu-full', 'tzx-gpu-devfreq', 'tzx-emmc-hs'):
    manifest = json.loads((Path('/usr/local/lib')/component/'manifest.json').read_text())
    for name, digest in manifest['files'].items():
        assert sha(Path(name).read_bytes()) == digest, name
assert not run('systemctl', '--failed', '--plain', '--no-legend').strip()
print(run('python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard'), end='', flush=True)
backup.mkdir(parents=True)
atomic(backup/'cpu-full-failure.json', (state/'cpu-full-failure.json').read_bytes())
atomic(backup/'cpu-full-revoked.json', proof)
atomic(backup/'shutdown-journal.txt', run('journalctl', '-b', '-1', '-u', 'tzx-cpu-dvfs', '--no-pager').encode())
atomic(backup/'fix_performance_shutdown.py', Path(__file__).read_bytes())
content = b'[Service]\n# Deliver graceful termination to the supervisor, allowing its child to finish.\n# Timeout still kills the complete cgroup; kernel leases remain unchanged.\nKillMode=mixed\n'
files = {}
for unit in ('tzx-cpu-dvfs', 'tzx-gpu-performance', 'tzx-emmc-hs'):
    path = Path('/etc/systemd/system')/(unit+'.service.d/99-clean-shutdown.conf')
    assert not path.exists()
    atomic(path, content, 0o644)
    files[str(path)] = sha(content)
run('systemd-analyze', 'verify', '--man=no', 'tzx-cpu-dvfs.service',
    'tzx-gpu-performance.service', 'tzx-emmc-hs.service')
run('systemctl', 'daemon-reload')
for unit in ('tzx-cpu-dvfs', 'tzx-gpu-performance', 'tzx-emmc-hs'):
    assert run('systemctl', 'show', unit, '-p', 'KillMode', '--value').strip() == 'mixed'
atomic(state/'cpu-full-qualified.json', proof)
run('systemctl', 'start', 'tzx-cpu-dvfs')


def settle():
    for attempt in range(80):
        p = Path('/run/tzx-cpu-dvfs.json')
        if p.exists():
            value = json.loads(p.read_text())
            if value.get('state') == 'active' and value.get('boot_id') == boot:
                assert value['maximum_khz'] == [1416000, 1800000]
                return
        time.sleep(.25)
    raise RuntimeError('CPU performance did not become active')


settle()
cycles = []
for cycle in range(2):
    run('systemctl', 'stop', 'tzx-emmc-hs', 'tzx-cpu-dvfs', 'tzx-gpu-performance')
    assert sha((state/'cpu-full-qualified.json').read_bytes()) == sha(proof)
    assert not (state/'cpu-full-pending.json').exists()
    assert not (state/'gpu-devfreq-pending.json').exists()
    assert not (state/'emmc-hs-pending.json').exists()
    assert not Path('/sys/module/tzx_cpufreq_dvfs_v2').exists()
    assert not Path('/sys/module/tzx_emmc_hs_lease').exists()
    assert int(Path('/sys/module/tzx_gpu_devfreq_guard/parameters/limit_mhz').read_text()) == 200
    assert not run('systemctl', '--failed', '--plain', '--no-legend').strip()
    run('systemctl', 'start', 'tzx-gpu-performance')
    run('systemctl', 'start', 'tzx-cpu-dvfs')
    settle()
    run('systemctl', 'start', 'tzx-emmc-hs', timeout=160)
    assert run('systemctl', 'is-active', 'tzx-gpu-performance', 'tzx-cpu-dvfs', 'tzx-emmc-hs').split() == ['active']*3
    cycles.append(dict(cycle=cycle+1, status='PASS', qualification_preserved=True,
                       CPU_480_GPU_200_storage_baselines_restored=True))
    print('PERFORMANCE_CLEAN_STOP_RESTART_PASS', cycle+1, flush=True)
record = dict(state='installed-two-stop-restart-cycles-passed', boot_id=boot, files=files,
    restored_exact_CPU_qualification_sha256=sha(proof), original_false_failure=failure,
    backup=str(backup), cycles=cycles, kernel_leases_unchanged=True,
    normal_reboot_verification='pending')
atomic(state/'performance-clean-shutdown.json', (json.dumps(record, indent=2)+'\n').encode())
os.sync()
print('PERFORMANCE_SUPERVISOR_CLEAN_SHUTDOWN_INSTALLED', json.dumps(record), flush=True)
