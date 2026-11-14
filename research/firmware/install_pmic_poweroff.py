"""Stage a reversible normal-poweroff handler, then qualify a real cold boot."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

p = argparse.ArgumentParser()
p.add_argument('operation', choices=('check', 'stage', 'test-poweroff', 'verify-cold-boot', 'enable', 'restore'))
a = p.parse_args()
assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
ROOT = Path('/root/tzx-recovery/pmic-poweroff')
STATE = Path('/var/lib/tzx/pmic-poweroff-installed.json')
RUNTIME = '/usr/local/lib/tzx-pmic-poweroff/runtime.py'
UNIT = 'tzx-pmic-poweroff.service'
sha = lambda value: hashlib.sha256(value).hexdigest()


def run(*command, timeout=45):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout).stdout.strip()


def atomic(path, data, mode=0o600):
    assert not path.is_symlink(), path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.pmic-new')
    with temporary.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fchmod(stream.fileno(), mode)
        os.fchown(stream.fileno(), 0, 0)
        os.fsync(stream.fileno())
    temporary.replace(path)
    syncdir(path.parent)
    assert path.read_bytes() == data


def syncdir(path):
    fd = os.open(path, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)


def record(path, value):
    atomic(path, json.dumps(value, indent=2).encode()+b'\n')


def status():
    return json.loads(run('python3', '/usr/local/lib/tzx-pmic-poweroff/read_pmic_shutdown_status.py'))


def desktop_health():
    run('python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard')
    health = json.loads(Path('/var/lib/tzx/dram-gpu-boot-health.json').read_text())
    assert health['boot_id'] == BOOT and health['status'] == 'PASS'
    for service in ('tzx-gpu', 'lightdm', 'tzx-dram-gpu-health', 'tzx-cpufreq', 'tzx-rtc-log'):
        assert run('systemctl', 'is-active', service+'.service') == 'active'
    assert run('systemctl', '--failed', '--no-legend') == ''


if a.operation in ('check', 'stage'):
    desktop_health()
    package = Path('/home/debian/pmic-poweroff-runtime.tar.gz').read_bytes()
    assert sha(package) == '71364eebcdae5e4687557273272a05eb3f0e5e444edfa521c4ca855c0834b9e3'
    with tarfile.open(fileobj=io.BytesIO(package), mode='r:gz') as archive:
        members = archive.getmembers()
        assert len(members) == 5 and len({m.name for m in members}) == 5
        assert all(m.isfile() and not PurePosixPath(m.name).is_absolute() and '..' not in PurePosixPath(m.name).parts and m.size < 2000000 for m in members)
        manifest = json.load(archive.extractfile('FILES.json'))
        assert {m.name for m in members} == set(manifest) | {'FILES.json'}
        files = {name: archive.extractfile(name).read() for name in manifest}
    assert set(files) == {'usr/local/lib/tzx-pmic-poweroff/tzx_pmic_poweroff.ko',
                          'usr/local/lib/tzx-pmic-poweroff/runtime.py',
                          'usr/local/lib/tzx-pmic-poweroff/read_pmic_shutdown_status.py',
                          'etc/systemd/system/'+UNIT}
    for name, data in files.items():
        assert sha(data) == manifest[name], name
        if name.endswith('.py'):
            compile(data, name, 'exec')
    print('PMIC_POWEROFF_PACKAGE_AND_DESKTOP_PREFLIGHT_PASS', flush=True)
    if a.operation == 'check':
        raise SystemExit(0)
    assert not ROOT.exists() and not STATE.exists()
    assert not Path('/sys/module/tzx_pmic_poweroff').exists()
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
    record(ROOT/'before.json', before)
    record(ROOT/'files.json', manifest)
    atomic(ROOT/'installer.py', Path(__file__).read_bytes())
    atomic(ROOT/'runtime-package.tar.gz', package)
    for name, data in files.items():
        atomic(Path('/')/name, data, 0o644)
    run('systemd-analyze', 'verify', '/etc/systemd/system/'+UNIT)
    run('systemctl', 'daemon-reload')
    print(run('python3', RUNTIME, 'verify'), flush=True)
    record(STATE, {'state': 'staged_manual_poweroff_pending', 'boot_id': BOOT, 'files': manifest,
                   'unit_enabled': False, 'poweroff_tested': False})
    print('PMIC_POWEROFF_STAGED_NOT_ENABLED', flush=True)
    raise SystemExit(0)

installed = json.loads(STATE.read_text())
for name, digest in installed['files'].items():
    path = Path('/')/name
    assert path.is_file() and not path.is_symlink() and sha(path.read_bytes()) == digest, name
if a.operation == 'restore':
    control = status()['axp717']['0x27']
    run('systemctl', 'disable', '--now', UNIT)
    run('python3', RUNTIME, 'remove')
    before = json.loads((ROOT/'before.json').read_text())
    assert status()['axp717']['0x27'] == control
    for name, previous in before.items():
        path = Path('/')/name
        if previous is None:
            path.unlink()
            syncdir(path.parent)
        else:
            data = (ROOT/'files'/name).read_bytes()
            assert sha(data) == previous['sha256']
            atomic(path, data, previous['mode'])
    run('systemctl', 'daemon-reload')
    record(STATE, dict(installed, state='removed_without_pmic_control_write', unit_enabled=False))
    print('PMIC_POWEROFF_REMOVED_WITHOUT_POWER_CYCLE', flush=True)
elif a.operation == 'test-poweroff':
    assert installed['state'] == 'staged_manual_poweroff_pending'
    assert not (ROOT/'cold-boot-test-intent.json').exists()
    desktop_health()
    # Accept a completed audit of this boot from either qualified baseline;
    # an active unit or a historical PASS is not a completed current audit.
    for audit_unit in ('tzx-cpu-cooling-boot-files.service', 'tzx-dram-gpu-final-files.service'):
        properties = run('systemctl', 'show', audit_unit, '-p', 'ActiveState', '-p', 'Result', '-p', 'ExecMainStatus')
        if not all(value in properties for value in ('ActiveState=inactive', 'Result=success', 'ExecMainStatus=0')):
            continue
        audit = run('journalctl', '-b', '-u', audit_unit, '-o', 'cat', '--no-pager')
        if 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS' in audit:
            break
    else:
        raise AssertionError('No completed passing file-integrity audit for the current boot')
    run('systemctl', 'start', UNIT)
    before = status()
    assert Path('/sys/module/tzx_pmic_poweroff/parameters/armed').read_text().strip() == 'Y'
    intent = {'state': 'software_poweroff_requested_physical_start_pending', 'boot_id': BOOT,
              'before': before, 'method': 'normal systemctl poweroff; SYS_OFF_MODE_POWER_OFF_PREPARE; AXP717 REG27 bit0 only',
              'manual_power_on_required': True}
    record(ROOT/'cold-boot-test-intent.json', intent)
    record(STATE, dict(installed, state=intent['state'], test_intent=intent))
    os.sync()
    print('PMIC_NORMAL_POWEROFF_TEST_READY', json.dumps(intent), flush=True)
    print(run('systemd-run', '--unit=tzx-pmic-normal-poweroff-test', '--on-active=3s',
              '/usr/bin/systemctl', 'poweroff'), flush=True)
elif a.operation == 'verify-cold-boot':
    intent = json.loads((ROOT/'cold-boot-test-intent.json').read_text())
    assert BOOT != intent['boot_id']
    desktop_health()
    now = status()
    assert int(now['axp717']['0x21'], 16) & 2, 'No retained PMIC software poweroff reason; do not claim cold boot'
    assert int(now['axp717']['0x21'], 16) & 0xf8 == 0, 'PMIC voltage/current/temperature shutdown reason'
    assert int(now['axp717']['0x27'], 16) & 0xf3 == 0
    proof = {'state': 'pmic_software_poweroff_and_full_memory_accelerated_cold_boot_verified',
             'boot_before': intent['boot_id'], 'boot_after': BOOT, 'pmic_status': now,
             'pmic_software_poweroff_cause': True, 'unit_enabled': False}
    record(ROOT/'cold-boot-result.json', proof)
    record(STATE, dict(installed, state=proof['state'], poweroff_tested=True, cold_boot_proof=proof))
    print('PMIC_SOFTWARE_POWEROFF_CAUSE_AND_ACCELERATED_COLD_BOOT_PASS', json.dumps(proof), flush=True)
elif a.operation == 'enable':
    assert installed['poweroff_tested'] is True
    assert installed['cold_boot_proof']['boot_after'] == BOOT
    desktop_health()
    run('systemctl', 'enable', '--now', UNIT)
    assert Path('/sys/module/tzx_pmic_poweroff/parameters/armed').read_text().strip() == 'Y'
    record(STATE, dict(installed, state='qualified_normal_poweroff_enabled', unit_enabled=True,
                       enabled_boot_id=BOOT))
    print('PMIC_NORMAL_POWEROFF_QUALIFIED_AND_ENABLED', flush=True)
