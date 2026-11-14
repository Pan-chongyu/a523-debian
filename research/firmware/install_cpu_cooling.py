"""Durable, reversible thermal-QoS addition to the trained DRAM/GPU baseline."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

p = argparse.ArgumentParser()
p.add_argument('operation', choices=('check', 'install-for-trial', 'enable-for-reboot', 'verify-boot', 'restore'))
a = p.parse_args()
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
ROOT = Path('/root/tzx-recovery/cpu-cooling')
STATE = Path('/var/lib/tzx/cpu-cooling-installed.json')
GPU = Path('/usr/local/lib/tzx-dram-gpu/runtime.py')
GPU_NAME = str(GPU).lstrip('/')
OLD = '7f2a58be42766a8a6af14171d972654d6006f69179bbb87eeb67dc4216282189'
NEW = 'f708504a8e430ef8259b3af6a0b2c0fbb8bf64ff7c534e51d8754aa322f12690'
UNIT = 'tzx-cpu-cooling.service'
BOOKS = [Path('/root/tzx-recovery/dram-gpu-runtime/installed-files.json'),
         Path('/var/lib/tzx/dram-gpu-runtime-installed.json'), Path('/var/lib/tzx/gpu-qualified')]
sha = lambda value: hashlib.sha256(value).hexdigest()


def syncdir(path):
    fd = os.open(path, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)


def atomic(path, data, mode=0o600):
    assert not path.is_symlink(), path
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.cooling-new')
    with temp.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fchmod(stream.fileno(), mode)
        os.fchown(stream.fileno(), 0, 0)
        os.fsync(stream.fileno())
    temp.replace(path)
    syncdir(path.parent)
    assert path.read_bytes() == data


def record(path, value):
    atomic(path, json.dumps(value, indent=2).encode()+b'\n')


def run(*command, timeout=50):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout).stdout.strip()


def update_books(old, new):
    for path in BOOKS:
        value = json.loads(path.read_text())
        hashes = value if path == BOOKS[0] else value['files']
        assert hashes[GPU_NAME] == old, path
        hashes[GPU_NAME] = new
        if path != BOOKS[0]:
            value['aggregate_thermal_inventory_support'] = new == NEW
        record(path, value)


def baseline():
    run('python3', str(GPU), 'guard')
    health = json.loads(Path('/var/lib/tzx/dram-gpu-boot-health.json').read_text())
    assert health['boot_id'] == BOOT and health['status'] == 'PASS'
    for service in ('tzx-cpufreq', 'tzx-thermal', 'tzx-gpu', 'lightdm', 'tzx-rtc-log'):
        assert run('systemctl', 'is-active', service+'.service') == 'active'
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096


if a.operation in ('check', 'install-for-trial'):
    baseline()
    assert not Path('/sys/module/tzx_cpu_cooling').exists()
    assert sha(GPU.read_bytes()) == OLD
    trial = json.loads(Path('/var/lib/tzx/cpu-cooling-trial.json').read_text())
    assert trial['boot_id'] == BOOT and trial['result'] == 'PASS'
    assert trial['module_sha256'] == 'd37b67d234a699a45eaf0c7f9c350123271754091a77c498a6f99e883ac37efa'
    assert len(trial['cycles']) == 2 and trial['file_audit'] == 'PASS'
    props = run('systemctl', 'show', 'tzx-cpu-cooling-trial.service',
                '-p', 'ActiveState', '-p', 'Result', '-p', 'ExecMainStatus')
    assert all(v in props for v in ('Result=success', 'ActiveState=inactive', 'ExecMainStatus=0'))
    package = Path('/home/debian/cpu-cooling-runtime.tar.gz').read_bytes()
    assert sha(package) == 'e8864f9e65224f9dd9bb9e1f02aa6c38b75fb0048fb06d1da11fda1b508ea34f'
    with tarfile.open(fileobj=io.BytesIO(package), mode='r:gz') as archive:
        members = archive.getmembers()
        assert len(members) == 5 and len({m.name for m in members}) == 5
        assert all(m.isfile() and not PurePosixPath(m.name).is_absolute() and '..' not in PurePosixPath(m.name).parts and m.size < 2000000 for m in members)
        hashes = json.load(archive.extractfile('FILES.json'))
        assert {m.name for m in members} == set(hashes) | {'FILES.json'}
        files = {name: archive.extractfile(name).read() for name in hashes}
    assert set(files) == {GPU_NAME, 'usr/local/lib/tzx-cpu-cooling/tzx_cpu_cooling.ko',
                          'usr/local/lib/tzx-cpu-cooling/runtime.py', 'etc/systemd/system/'+UNIT}
    for name, data in files.items():
        assert sha(data) == hashes[name]
        if name.endswith('.py'):
            compile(data, name, 'exec')
    assert hashes[GPU_NAME] == NEW
    print('CPU_COOLING_MANUAL_TRIP_AND_PACKAGE_PREFLIGHT_PASS', flush=True)
    if a.operation == 'check':
        raise SystemExit(0)
    assert not ROOT.exists() and not STATE.exists()
    before = {}
    for name in files:
        path = Path('/')/name
        assert not path.is_symlink()
        if path.exists():
            data = path.read_bytes()
            atomic(ROOT/'files'/name, data)
            before[name] = {'sha256': sha(data), 'mode': path.stat().st_mode & 0o777}
        else:
            before[name] = None
    for path in BOOKS:
        atomic(ROOT/'bookkeeping-before'/str(path).lstrip('/'), path.read_bytes())
    record(ROOT/'before.json', before)
    record(ROOT/'files.json', hashes)
    atomic(ROOT/'installer.py', Path(__file__).read_bytes())
    atomic(ROOT/'runtime-package.tar.gz', package)
    for name, data in files.items():
        atomic(Path('/')/name, data, 0o644)
    update_books(OLD, NEW)
    run('systemd-analyze', 'verify', '/etc/systemd/system/'+UNIT)
    run('systemctl', 'daemon-reload')
    record(STATE, {'state': 'installed_for_manual_coexistence_trial', 'boot_id': BOOT,
                   'files': hashes, 'unit_enabled': False, 'lowered_trip_proof': trial,
                   'gpu_runtime_inventory_only_change': {'before': OLD, 'after': NEW}})
    run('systemctl', 'start', UNIT)
    print(run('python3', '/usr/local/lib/tzx-cpu-cooling/runtime.py', 'verify'), flush=True)
    pending = Path('/var/lib/tzx/dram-gpu-boot-pending.json')
    assert not pending.exists()
    record(pending, {'boot_id': BOOT, 'health': 'aggregate_thermal_inventory_update_check'})
    run('systemctl', 'restart', 'tzx-dram-gpu-health.service', timeout=115)
    assert not pending.exists()
    print('CPU_COOLING_INSTALLED_GPU_HEALTH_WITH_SIX_ZONES_PASS_NOT_ENABLED', flush=True)
    raise SystemExit(0)

installed = json.loads(STATE.read_text())
for name, digest in installed['files'].items():
    path = Path('/')/name
    assert path.is_file() and not path.is_symlink() and sha(path.read_bytes()) == digest, name
if a.operation == 'restore':
    run('systemctl', 'disable', '--now', UNIT)
    run('python3', '/usr/local/lib/tzx-cpu-cooling/runtime.py', 'stop')
    before = json.loads((ROOT/'before.json').read_text())
    for name, previous in before.items():
        path = Path('/')/name
        if previous is None:
            path.unlink()
            syncdir(path.parent)
        else:
            data = (ROOT/'files'/name).read_bytes()
            assert sha(data) == previous['sha256']
            atomic(path, data, previous['mode'])
    update_books(NEW, OLD)
    run('systemctl', 'daemon-reload')
    record(STATE, dict(installed, state='thermal_addition_removed_original_gpu_inventory_restored', unit_enabled=False))
    print('CPU_COOLING_QOS_REMOVED_ORIGINAL_GPU_RUNTIME_RESTORED', flush=True)
elif a.operation == 'enable-for-reboot':
    baseline()
    assert installed['state'] == 'installed_for_manual_coexistence_trial'
    run('python3', '/usr/local/lib/tzx-cpu-cooling/runtime.py', 'verify')
    props = run('systemctl', 'show', 'tzx-cpu-cooling-gpu-coexistence.service',
                '-p', 'Result', '-p', 'ActiveState', '-p', 'ExecMainStatus')
    assert all(v in props for v in ('Result=success', 'ActiveState=inactive', 'ExecMainStatus=0'))
    log = run('journalctl', '-b', '-u', 'tzx-cpu-cooling-gpu-coexistence.service', '-o', 'cat', '--no-pager')
    assert 'CPU_COOLING_GPU_FILES_AND_LIFECYCLE_PASS' in log
    assert not any(s in log for s in ('Traceback', 'MISMATCH', 'CORRUPTION'))
    run('systemctl', 'enable', UNIT)
    record(STATE, dict(installed, state='coexistence_passed_autostart_reboot_pending',
                       unit_enabled=True, coexistence_proof_journal_sha256=sha(log.encode())))
    os.sync()
    print('CPU_COOLING_COEXISTENCE_PASSED_AUTOSTART_REBOOT_PENDING', flush=True)
    print(run('systemd-run', '--unit=tzx-cpu-cooling-autostart-reboot', '--on-active=3s',
              '/usr/bin/systemctl', 'reboot'), flush=True)
else:
    assert installed['boot_id'] != BOOT and installed['unit_enabled'] is True
    baseline()
    assert run('systemctl', 'is-active', UNIT) == 'active'
    assert run('systemctl', '--failed', '--no-legend') == ''
    check = run('python3', '/usr/local/lib/tzx-cpu-cooling/runtime.py', 'verify')
    assert 'TZX_CPU_COOLING_PRODUCTION_ZONE_AND_QOS_PASS' in check
    record(STATE, dict(installed, state='lowered_trips_coexistence_and_actual_autostart_verified',
                       verified_boot_id=BOOT, production_check=check, failed_units=0))
    print('CPU_COOLING_STANDARD_THERMAL_QOS_AUTOSTART_PASS', check, flush=True)
