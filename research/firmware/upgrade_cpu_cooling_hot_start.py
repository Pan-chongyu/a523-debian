"""Qualify the hot-start guard fix, preserving the complete v1 rollback."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

parser = argparse.ArgumentParser()
parser.add_argument('operation', choices=('trial', 'apply'))
args = parser.parse_args()
assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
UNIT = 'tzx-cpu-cooling.service'
STATE = Path('/var/lib/tzx/cpu-cooling-installed.json')
BACKUP = Path('/root/tzx-recovery/cpu-cooling-hot-start-v2')
NEW_MODULE = 'd37b67d234a699a45eaf0c7f9c350123271754091a77c498a6f99e883ac37efa'
sha = lambda data: hashlib.sha256(data).hexdigest()


def run(*command, timeout=40):
    return subprocess.run(command, check=True, timeout=timeout)


def atomic(path, data, mode=0o600):
    assert not path.is_symlink(), path
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.hot-start-new')
    with temp.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fchmod(stream.fileno(), mode)
        os.fchown(stream.fileno(), 0, 0)
        os.fsync(stream.fileno())
    temp.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)
    assert path.read_bytes() == data


state = json.loads(STATE.read_text())
assert state['state'] == 'lowered_trips_coexistence_and_actual_autostart_verified'
assert state['verified_boot_id'] == BOOT and state['unit_enabled'] is True
assert 'hot_start_guard_revision' not in state
for name, digest in state['files'].items():
    assert sha((Path('/')/name).read_bytes()) == digest, name
run('python3', '/usr/local/lib/tzx-cpu-cooling/runtime.py', 'verify')
assert not subprocess.check_output(['systemctl', '--failed', '--no-legend'], text=True).strip()
if args.operation == 'trial':
    assert sha(Path('/home/debian/tzx_cpu_cooling.ko').read_bytes()) == NEW_MODULE
    run('systemctl', 'stop', UNIT)
    try:
        run('python3', '-u', '/home/debian/verify_cpu_cooling_trial.py', timeout=180)
    finally:
        if Path('/sys/module/tzx_cpu_cooling').exists():
            run('rmmod', 'tzx_cpu_cooling')
        run('systemctl', 'start', UNIT)
    run('python3', '/usr/local/lib/tzx-cpu-cooling/runtime.py', 'verify')
    print('CPU_COOLING_V2_LOWERED_TRIPS_PASS_V1_PRODUCTION_RESTORED', flush=True)
    raise SystemExit(0)

trial = json.loads(Path('/var/lib/tzx/cpu-cooling-trial.json').read_text())
assert trial['boot_id'] == BOOT and trial['module_sha256'] == NEW_MODULE
assert trial['result'] == 'PASS' and len(trial['cycles']) == 2 and trial['file_audit'] == 'PASS'
assert not BACKUP.exists()
package = Path('/home/debian/cpu-cooling-runtime-v2.tar.gz').read_bytes()
assert sha(package) == 'e8864f9e65224f9dd9bb9e1f02aa6c38b75fb0048fb06d1da11fda1b508ea34f'
with tarfile.open(fileobj=io.BytesIO(package), mode='r:gz') as archive:
    members = archive.getmembers()
    assert len(members) == 5 and len({m.name for m in members}) == 5
    assert all(m.isfile() and not PurePosixPath(m.name).is_absolute() and '..' not in PurePosixPath(m.name).parts for m in members)
    manifest = json.load(archive.extractfile('FILES.json'))
    assert {m.name for m in members} == set(manifest) | {'FILES.json'}
    assert set(manifest) == set(state['files'])
    files = {name: archive.extractfile(name).read() for name in manifest}
for name, data in files.items():
    assert sha(data) == manifest[name], name
    if name.endswith('.py'):
        compile(data, name, 'exec')
assert manifest['usr/local/lib/tzx-cpu-cooling/tzx_cpu_cooling.ko'] == NEW_MODULE
changed = {name for name in manifest if manifest[name] != state['files'][name]}
assert changed == {'usr/local/lib/tzx-cpu-cooling/tzx_cpu_cooling.ko', 'usr/local/lib/tzx-cpu-cooling/runtime.py'}
atomic(BACKUP/'state-before.json', STATE.read_bytes())
atomic(BACKUP/'files-before.json', Path('/root/tzx-recovery/cpu-cooling/files.json').read_bytes())
atomic(BACKUP/'runtime-package.tar.gz', package)
atomic(BACKUP/'files.json', json.dumps(manifest, indent=2).encode()+b'\n')
atomic(BACKUP/'installer.py', Path(__file__).read_bytes())
for name in changed:
    atomic(BACKUP/'files'/name, (Path('/')/name).read_bytes())
run('systemctl', 'stop', UNIT)
try:
    for name in changed:
        atomic(Path('/')/name, files[name], 0o644)
    run('systemctl', 'start', UNIT)
    run('python3', '/usr/local/lib/tzx-cpu-cooling/runtime.py', 'verify')
except BaseException:
    run('systemctl', 'stop', UNIT)
    for name in changed:
        atomic(Path('/')/name, (BACKUP/'files'/name).read_bytes(), 0o644)
    run('systemctl', 'reset-failed', UNIT)
    run('systemctl', 'start', UNIT)
    raise
state.update(state='installed_for_manual_coexistence_trial', files=manifest,
             hot_start_guard_revision=2, hot_start_valid_sensor_max_mC=125000,
             lowered_trip_proof=trial, upgrade_boot_id=BOOT)
atomic(STATE, json.dumps(state, indent=2).encode()+b'\n')
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
os.sync()
print('CPU_COOLING_V2_HOT_START_GUARD_FIX_INSTALLED_NOT_REQUALIFIED', flush=True)
