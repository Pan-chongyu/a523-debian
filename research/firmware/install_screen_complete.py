"""Trial/install only the display function revision, with an exact local rollback."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time

p = argparse.ArgumentParser()
p.add_argument('operation', choices=('trial', 'enable', 'restore'))
a = p.parse_args()
assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
BACKUP = Path('/root/tzx-recovery/screen-functions-v1')
STATE = Path('/var/lib/tzx/screen-installed.json')
DROPIN = Path('/etc/systemd/system/tzx-display.service.d/98-screen.conf')
TRIAL_DROPIN = Path('/run/systemd/system/tzx-display.service.d/98-screen.conf')
QUALIFIED = Path('/var/lib/tzx/screen-qualified.json')


def run(*cmd, timeout=75, **kwargs):
    return subprocess.run(cmd, check=True, timeout=timeout, **kwargs)


def atomic(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.screen-new')
    with tmp.open('wb') as f:
        f.write(data)
        os.fchmod(f.fileno(), mode)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)


def record(path, value):
    atomic(path, (json.dumps(value, indent=2)+'\n').encode(), 0o600)


def halt():
    units = ['tzx-dram-gpu-health.service', 'lightdm.service']
    if Path('/etc/systemd/system/tzx-screen-health.service').exists():
        units.insert(0, 'tzx-screen-health.service')
    run('systemctl', 'stop', *units)
    run('systemctl', 'stop', 'tzx-gpu.service')
    if Path('/sys/module/tzx_gpu_nodes').exists():
        run('modprobe', '-r', 'tzx_gpu_nodes')
    if Path('/sys/module/panfrost').exists():
        run('modprobe', '-r', 'panfrost')
    assert not Path('/sys/module/panfrost').exists()
    run('systemctl', 'stop', 'tzx-display.service')
    assert not Path('/sys/module/tzx_display').exists()


def start(health=True):
    run('systemctl', 'daemon-reload')
    run('systemctl', 'start', 'tzx-display.service')
    run('systemctl', 'start', 'tzx-gpu.service')
    run('systemctl', 'start', 'lightdm.service')
    run('systemctl', 'restart', 'tzx-dram-gpu-health.service', timeout=110)
    if health:
        run('systemctl', 'start', 'tzx-screen-health.service', timeout=110)


def restore():
    halt()
    if Path('/etc/systemd/system/tzx-screen-health.service').exists():
        run('systemctl', 'disable', 'tzx-screen-health.service')
    TRIAL_DROPIN.unlink(missing_ok=True)
    for name, old in json.loads((BACKUP/'before.json').read_text())['files'].items():
        path = Path('/')/name
        if old is None:
            path.unlink(missing_ok=True)
        else:
            data = (BACKUP/'files'/name).read_bytes()
            assert hashlib.sha256(data).hexdigest() == old['sha256']
            atomic(path, data, old['mode'])
    QUALIFIED.unlink(missing_ok=True)
    Path('/var/lib/tzx/screen-boot-pending.json').unlink(missing_ok=True)
    start(health=False)
    record(STATE, {'state': 'original_display_restored', 'boot_id': BOOT, 'backup': str(BACKUP)})
    print('TZX_SCREEN_ORIGINAL_RESTORED', flush=True)


if a.operation == 'trial':
    assert not STATE.exists() and not TRIAL_DROPIN.exists()
    assert not DROPIN.exists()
    assert Path('/var/lib/tzx/gpu-qualified').exists()
    run('python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard')
    manifest = json.loads(Path('/home/debian/screen-FILES.json').read_text())
    package = Path('/home/debian/screen-runtime.tar.gz').read_bytes()
    assert hashlib.sha256(package).hexdigest() == manifest['package_sha256']
    assert len(manifest['files']) == 7
    with tarfile.open(fileobj=io.BytesIO(package), mode='r:gz') as archive:
        assert set(archive.getnames()) == set(manifest['files'])
        files = {}
        for item in archive.getmembers():
            assert item.isfile() and not item.name.startswith('/') and '..' not in Path(item.name).parts
            data = archive.extractfile(item).read()
            assert hashlib.sha256(data).hexdigest() == manifest['files'][item.name]['sha256']
            files[item.name] = data
    if BACKUP.exists():
        # The first preflight stopped before changing any installed files.
        # Permit that exact state only, retaining the original failed attempt.
        before = json.loads((BACKUP/'before.json').read_text())
        assert before['boot_id'] == BOOT
        assert set(before['files']) == set(files)
        assert all(old is None and not (Path('/')/name).exists()
                   for name, old in before['files'].items())
        assert (BACKUP/'package.tar.gz').read_bytes() == package
        atomic(BACKUP/'install_screen_complete-lifecycle-fixed.py', Path(__file__).read_bytes(), 0o600)
    else:
        BACKUP.mkdir(parents=True)
        old_files = {}
        for name in files:
            path = Path('/')/name
            if path.exists():
                assert not path.is_symlink()
                data = path.read_bytes()
                old_files[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'mode': path.stat().st_mode & 0o777}
                atomic(BACKUP/'files'/name, data, old_files[name]['mode'])
            else:
                old_files[name] = None
        record(BACKUP/'before.json', {'boot_id': BOOT, 'files': old_files})
        atomic(BACKUP/'package.tar.gz', package, 0o600)
        atomic(BACKUP/'install_screen_complete.py', Path(__file__).read_bytes(), 0o600)
        record(BACKUP/'FILES.json', manifest)
        # Keep rollback evidence for the untouched accelerated/software display paths.
        for name in ('dram-gpu-runtime-installed.json', 'gpu-qualified', 'cpu-cooling-installed.json'):
            atomic(BACKUP/name, (Path('/var/lib/tzx')/name).read_bytes(), 0o600)
    try:
        halt()
        for name, data in files.items():
            if name == str(DROPIN).lstrip('/'):
                text = data.decode().replace('runtime.py start\n', 'runtime.py start --trial\n')
                atomic(TRIAL_DROPIN, text.encode())
            else:
                atomic(Path('/')/name, data, manifest['files'][name]['mode'])
        record(STATE, {'state': 'manual_trial_running', 'installed_boot_id': BOOT,
                       'files': manifest['files'], 'package_sha256': manifest['package_sha256']})
        start()
        run('python3', '/home/debian/verify_screen_controls.py', timeout=30)
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
        assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
        state = json.loads(STATE.read_text())
        state['state'] = 'manual_driver_and_brightness_DPMS_passed_pending_rotation'
        record(STATE, state)
        print('TZX_SCREEN_MANUAL_DRIVER_PASS', flush=True)
    except BaseException:
        restore()
        raise
elif a.operation == 'enable':
    state = json.loads(STATE.read_text())
    assert state['state'] == 'manual_driver_and_brightness_DPMS_passed_pending_rotation'
    rotation = json.loads(Path('/var/lib/tzx/screen-rotation-test.json').read_text())
    assert rotation['boot_id'] == BOOT and rotation['result'] == 'PASS'
    assert len(rotation['tests']) >= 4
    health = json.loads(Path('/var/lib/tzx/screen-boot-health.json').read_text())
    assert health['boot_id'] == BOOT and health['result'] == 'PASS'
    run('systemctl', 'is-active', '--quiet', 'tzx-screen-health.service', 'tzx-dram-gpu-health.service', 'lightdm')
    files = json.loads((BACKUP/'FILES.json').read_text())['files']
    for name, item in files.items():
        if name != str(DROPIN).lstrip('/'):
            assert hashlib.sha256((Path('/')/name).read_bytes()).hexdigest() == item['sha256'], name
    record(QUALIFIED, {'profile': 'screen-functions-1', 'boot_id': BOOT,
                       'manual_backlight_DPMS_and_rotation': True, 'module_sha256': health['module_sha256']})
    with tarfile.open(BACKUP/'package.tar.gz', 'r:gz') as archive:
        atomic(DROPIN, archive.extractfile(str(DROPIN).lstrip('/')).read())
    TRIAL_DROPIN.unlink()
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', 'tzx-screen-health.service')
    state['state'] = 'manual_display_verified_enabled_pending_reboot'
    record(STATE, state)
    os.sync()
    print('TZX_SCREEN_ENABLED_PENDING_REBOOT', flush=True)
elif a.operation == 'restore':
    restore()
