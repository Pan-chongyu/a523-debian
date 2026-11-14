"""Stage hardware frame events independently, retaining the qualified screen v1."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

p = argparse.ArgumentParser()
p.add_argument('operation', choices=('trial', 'recover-trial', 'enable', 'restore'))
a = p.parse_args()
assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
ROOT = Path('/var/lib/tzx')
STATE = ROOT/'screen-installed.json'
QUALIFIED = ROOT/'screen-qualified.json'
PENDING = ROOT/'screen-boot-pending.json'
BACKUP = Path('/root/tzx-recovery/screen-hardware-vblank')
TRIAL = Path('/run/systemd/system/tzx-display.service.d/99-screen-vblank-trial.conf')
PROFILE = 'screen-functions-2-vblank'


def run(*cmd, timeout=80):
    return subprocess.run(cmd, check=True, timeout=timeout)


def atomic(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.vblank-new')
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
    atomic(path, (json.dumps(value, indent=2)+'\n').encode())


def halt():
    run('systemctl', 'stop', 'tzx-screen-health', 'tzx-dram-gpu-health', 'lightdm')
    run('systemctl', 'stop', 'tzx-gpu')
    for module in ('tzx_gpu_nodes', 'panfrost'):
        if (Path('/sys/module')/module).exists():
            run('modprobe', '-r', module)
    run('systemctl', 'stop', 'tzx-display')
    assert not Path('/sys/module/tzx_display').exists()


def start():
    run('systemctl', 'daemon-reload')
    for unit in ('tzx-display', 'tzx-gpu', 'lightdm'):
        run('systemctl', 'start', unit)
    run('systemctl', 'restart', 'tzx-dram-gpu-health', timeout=110)
    run('systemctl', 'start', 'tzx-screen-health', timeout=110)
    saved = BACKUP/'before-live-settings.json'
    if saved.exists():
        value = json.loads(saved.read_text())['brightness']
        Path('/sys/class/backlight/tzx-panel/brightness').write_text(str(value)+'\n')


def restore():
    halt()
    before = json.loads((BACKUP/'before-state.json').read_text())
    for name, item in before['files'].items():
        data = (BACKUP/'files'/name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == item['sha256'], name
        atomic(Path('/')/name, data, item['mode'])
    atomic(STATE, (BACKUP/'before-state.json').read_bytes())
    atomic(QUALIFIED, (BACKUP/'before-qualified.json').read_bytes())
    TRIAL.unlink(missing_ok=True)
    PENDING.unlink(missing_ok=True)
    start()
    record(ROOT/'screen-vblank-rollback.json', {'boot_id': BOOT, 'result': 'screen_v1_restored'})
    print('TZX_SCREEN_VBLANK_RESTORED_V1', flush=True)


if a.operation == 'trial':
    state = json.loads(STATE.read_text())
    assert state['state'] == 'manual_display_and_actual_autostart_verified'
    assert state['verified_boot_id'] == BOOT
    assert json.loads(QUALIFIED.read_text())['profile'] == 'screen-functions-1'
    assert not PENDING.exists() and not TRIAL.exists() and not BACKUP.exists()
    manifest_data = Path('/home/debian/screen-vblank-FILES.json').read_bytes()
    manifest = json.loads(manifest_data)
    package = Path('/home/debian/screen-runtime-vblank.tar.gz').read_bytes()
    assert hashlib.sha256(package).hexdigest() == manifest['package_sha256']
    assert set(manifest['files']) == set(state['files']) and len(state['files']) == 7
    files = {}
    with tarfile.open(fileobj=io.BytesIO(package), mode='r:gz') as archive:
        assert set(archive.getnames()) == set(manifest['files'])
        for entry in archive.getmembers():
            assert entry.isfile() and not entry.name.startswith('/') and '..' not in Path(entry.name).parts
            data = archive.extractfile(entry).read()
            assert hashlib.sha256(data).hexdigest() == manifest['files'][entry.name]['sha256']
            files[entry.name] = data
    changed = {name for name, item in state['files'].items()
               if item['sha256'] != manifest['files'][name]['sha256']}
    assert changed == {'usr/local/lib/tzx-screen/tzx_display.ko', 'usr/local/lib/tzx-screen/runtime.py'}
    for name, item in state['files'].items():
        assert hashlib.sha256((Path('/')/name).read_bytes()).hexdigest() == item['sha256'], name
    run('python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard')
    BACKUP.mkdir(parents=True)
    record(BACKUP/'before-live-settings.json',
           {'brightness': int(Path('/sys/class/backlight/tzx-panel/brightness').read_text())})
    for name in state['files']:
        atomic(BACKUP/'files'/name, (Path('/')/name).read_bytes(), state['files'][name]['mode'])
    for name, data in {'before-state.json': STATE.read_bytes(), 'before-qualified.json': QUALIFIED.read_bytes(),
                       'before-health.json': (ROOT/'screen-boot-health.json').read_bytes(),
                       'new-package.tar.gz': package, 'new-FILES.json': manifest_data,
                       'upgrader.py': Path(__file__).read_bytes()}.items():
        atomic(BACKUP/name, data)
    try:
        halt()
        for name in changed:
            atomic(Path('/')/name, files[name], manifest['files'][name]['mode'])
        drop = files['etc/systemd/system/tzx-display.service.d/98-screen.conf'].decode()
        assert drop.count('runtime.py start\n') == 1
        atomic(TRIAL, drop.replace('runtime.py start\n', 'runtime.py start --trial\n').encode(), 0o644)
        state.update(state='vblank_manual_trial_running', vblank_installed_boot_id=BOOT,
                     screen_v1_installed_boot_id=state['installed_boot_id'], installed_boot_id=BOOT,
                     files=manifest['files'], package_sha256=manifest['package_sha256'],
                     profile=PROFILE, vblank_backup=str(BACKUP))
        record(STATE, state)
        start()
        assert Path('/sys/module/tzx_display/parameters/screen_revision').read_text().strip() == PROFILE
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
        assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
        print('TZX_SCREEN_VBLANK_MANUAL_TRIAL_READY', flush=True)
    except BaseException:
        restore()
        raise
elif a.operation == 'recover-trial':
    # One identified harness error repeated health without its startup marker.
    # Require its precise journal and unchanged original qualification before recovery.
    state = json.loads(STATE.read_text())
    assert state['vblank_installed_boot_id'] == BOOT and state['profile'] == PROFILE
    assert state['state'] in ('vblank_manual_trial_running', 'manual_display_and_actual_autostart_verified')
    assert not Path('/var/lib/tzx/gpu-qualified').exists() and TRIAL.exists()
    revoked = json.loads((ROOT/'dram-gpu-revoked.json').read_text())
    original = Path('/root/tzx-recovery/screen-functions-v1/gpu-qualified').read_bytes()
    assert revoked['boot_id'] == BOOT and revoked['previous'] == json.loads(original)
    journal = subprocess.check_output(['journalctl', '-b', '-u', 'tzx-dram-gpu-health', '-o', 'cat', '--no-pager'], text=True)
    assert "FileNotFoundError: [Errno 2] No such file or directory: '/var/lib/tzx/dram-gpu-boot-pending.json'" in journal
    run('python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard')
    atomic(BACKUP/'harness-health-revoked.json', (ROOT/'dram-gpu-revoked.json').read_bytes())
    atomic(BACKUP/'harness-health-journal.txt', journal.encode())
    halt()
    atomic(ROOT/'gpu-qualified', original)
    state.update(state='vblank_manual_trial_running', installed_boot_id=BOOT,
                 screen_v1_installed_boot_id=json.loads((BACKUP/'before-state.json').read_text())['installed_boot_id'])
    record(STATE, state)
    start()
    for unit in ('tzx-dram-gpu-health', 'tzx-screen-pageflip-check', 'tzx-screen-harness-recover'):
        if subprocess.run(['systemctl', 'is-failed', '--quiet', unit]).returncode == 0:
            run('systemctl', 'reset-failed', unit)
    print('TZX_SCREEN_VBLANK_HARNESS_RECOVERED_ACCELERATED_DESKTOP', flush=True)
elif a.operation == 'enable':
    state = json.loads(STATE.read_text())
    assert state['state'] == 'vblank_manual_trial_running' and state['vblank_installed_boot_id'] == BOOT
    for name, item in state['files'].items():
        assert hashlib.sha256((Path('/')/name).read_bytes()).hexdigest() == item['sha256'], name
    for name in ('screen-vblank-test.json', 'screen-rotation-test.json', 'screen-controls-test.json'):
        proof = json.loads((ROOT/name).read_text())
        assert proof['boot_id'] == BOOT and proof['result'] == 'PASS', name
    assert json.loads((ROOT/'screen-boot-health.json').read_text())['revision'] == PROFILE
    assert not PENDING.exists()
    assert not subprocess.check_output(['systemctl', '--failed', '--no-legend'], text=True).strip()
    record(QUALIFIED, {'profile': PROFILE, 'boot_id': BOOT, 'hardware_vblank_DPMS_rotation': True,
                       'module_sha256': state['files']['usr/local/lib/tzx-screen/tzx_display.ko']['sha256']})
    TRIAL.unlink()
    run('systemctl', 'daemon-reload')
    state.update(state='vblank_verified_enabled_pending_reboot')
    record(STATE, state)
    os.sync()
    print('TZX_SCREEN_VBLANK_ENABLED_PENDING_REBOOT', flush=True)
else:
    restore()
