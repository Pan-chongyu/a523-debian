"""Trial RCQ buffer switches with an exact rollback to the boot-qualified v3."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

p = argparse.ArgumentParser()
p.add_argument('operation', choices=('trial', 'enable', 'restore'))
a = p.parse_args()
assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
ROOT = Path('/var/lib/tzx')
STATE = ROOT/'screen-installed.json'
QUALIFIED = ROOT/'screen-qualified.json'
PENDING = ROOT/'screen-boot-pending.json'
BACKUP = Path('/root/tzx-recovery/screen-standby')
TRIAL = Path('/run/systemd/system/tzx-display.service.d/99-screen-standby-trial.conf')
PROFILE = 'screen-functions-4-standby'


def run(*cmd, timeout=80):
    return subprocess.run(cmd, check=True, timeout=timeout)


def atomic(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.standby-new')
    with temp.open('wb') as f:
        f.write(data)
        os.fchmod(f.fileno(), mode)
        f.flush()
        os.fsync(f.fileno())
    temp.replace(path)
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
    settings = json.loads((BACKUP/'before-live-settings.json').read_text())
    Path('/sys/class/backlight/tzx-panel/brightness').write_text(str(settings['brightness'])+'\n')
    for attempt in range(30):
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                if proc.stat().st_uid == 1000 and (proc/'comm').read_text().strip() == 'xfce4-session':
                    values = dict(v.split('=', 1) for v in (proc/'environ').read_bytes().decode().split('\0') if '=' in v)
                    if 'XAUTHORITY' in values:
                        run('runuser', '-u', 'debian', '--', 'env', 'DISPLAY='+values['DISPLAY'],
                            'XAUTHORITY='+values['XAUTHORITY'], '/usr/local/bin/tzx-screen', '--rotate', settings['rotation'])
                        return
            except (OSError, ValueError):
                continue
        import time
        time.sleep(1)
    raise RuntimeError('No authenticated Xfce session available for saved orientation')


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
    print('TZX_SCREEN_STANDBY_RESTORED_V3', flush=True)


if a.operation == 'trial':
    state = json.loads(STATE.read_text())
    assert state['state'] == 'manual_display_and_actual_autostart_verified' and state['verified_boot_id'] == BOOT
    assert state['profile'] == 'screen-functions-3-doublebuffer'
    assert json.loads(QUALIFIED.read_text())['profile'] == state['profile']
    assert not PENDING.exists() and not TRIAL.exists() and not BACKUP.exists()
    manifest_data = Path('/home/debian/screen-standby-FILES.json').read_bytes()
    manifest = json.loads(manifest_data)
    package = Path('/home/debian/screen-runtime-standby.tar.gz').read_bytes()
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
    settings = json.loads(Path('/home/debian/.config/tzx-screen.json').read_text())
    settings['brightness'] = int(Path('/sys/class/backlight/tzx-panel/brightness').read_text())
    record(BACKUP/'before-live-settings.json', settings)
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
        # A manual candidate failure is rolled back by this process. Avoid a
        # concurrent global OnFailure handler racing that normal rollback.
        drop = '[Unit]\nOnFailure=\n'+drop
        atomic(TRIAL, drop.replace('runtime.py start\n', 'runtime.py start --trial\n').encode(), 0o644)
        state.update(state='standby_manual_trial_running', standby_installed_boot_id=BOOT,
                     previous_revision_installed_boot_id=state['installed_boot_id'], installed_boot_id=BOOT,
                     files=manifest['files'], package_sha256=manifest['package_sha256'],
                     profile=PROFILE, standby_backup=str(BACKUP))
        record(STATE, state)
        start()
        assert int(Path('/sys/module/tzx_display/parameters/screen_buffer_errors').read_text()) == 0
        assert int(Path('/sys/module/tzx_display/parameters/screen_buffer_commits').read_text()) > 0
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
        assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
        print('TZX_SCREEN_STANDBY_MANUAL_TRIAL_READY', flush=True)
    except BaseException:
        restore()
        raise
elif a.operation == 'enable':
    state = json.loads(STATE.read_text())
    assert state['state'] == 'standby_manual_trial_running' and state['installed_boot_id'] == BOOT
    assert state['settings_save_revision'] == 2
    for name, item in state['files'].items():
        assert hashlib.sha256((Path('/')/name).read_bytes()).hexdigest() == item['sha256'], name
    for name in ('screen-vblank-test.json', 'screen-rotation-test.json', 'screen-controls-test.json',
                 'screen-pageflip-test.json', 'screen-standby-test.json', 'screen-doublebuffer-test.json', 'screen-settings-concurrency.json'):
        proof = json.loads((ROOT/name).read_text())
        assert proof['boot_id'] == BOOT and proof['result'] == 'PASS', name
    pageflip = json.loads((ROOT/'screen-pageflip-test.json').read_text())
    assert pageflip['buffer_address_commits'] > 300
    assert int(Path('/sys/module/tzx_display/parameters/screen_buffer_errors').read_text()) == 0
    assert json.loads((ROOT/'screen-boot-health.json').read_text())['revision'] == PROFILE
    assert int(Path('/sys/module/tzx_display/parameters/screen_panel_errors').read_text()) == 0
    assert Path('/sys/module/tzx_display/parameters/screen_panel_sleeping').read_text().strip() == 'N'
    assert not PENDING.exists()
    assert not subprocess.check_output(['systemctl', '--failed', '--no-legend'], text=True).strip()
    record(QUALIFIED, {'profile': PROFILE, 'boot_id': BOOT, 'RCQ_vblank_DPMS_rotation': True, 'panel_DCS_sleep': True,
                       'module_sha256': state['files']['usr/local/lib/tzx-screen/tzx_display.ko']['sha256']})
    TRIAL.unlink()
    run('systemctl', 'daemon-reload')
    state.update(state='standby_verified_enabled_pending_reboot')
    record(STATE, state)
    os.sync()
    print('TZX_SCREEN_STANDBY_ENABLED_PENDING_REBOOT', flush=True)
else:
    restore()
