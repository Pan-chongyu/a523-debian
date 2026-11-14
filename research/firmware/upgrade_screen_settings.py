"""Replace only the screen settings app, retaining the qualified display build."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import tarfile
import time

p = argparse.ArgumentParser()
p.add_argument('operation', choices=('install', 'restore'))
a = p.parse_args()
assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
ROOT = Path('/var/lib/tzx')
STATE = ROOT/'screen-installed.json'
BACKUP = Path('/root/tzx-recovery/screen-settings-save-v2')
APP = Path('/usr/local/bin/tzx-screen')
OLD = '2ececea6e21c539daaa5d4be5e29f387510c94085a6ef4f7edbe2906b956c35f'
assert not (ROOT/'screen-boot-pending.json').exists()


def atomic(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.settings-new')
    with temp.open('wb') as f:
        f.write(data)
        os.fchmod(f.fileno(), mode)
        f.flush()
        os.fsync(f.fileno())
    temp.replace(path)
    descriptor = os.open(path.parent, os.O_DIRECTORY)
    os.fsync(descriptor)
    os.close(descriptor)


def restart_daemon():
    values = None
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            if proc.stat().st_uid != 1000:
                continue
            if (proc/'comm').read_text().strip() == 'xfce4-session':
                values = dict(v.split('=', 1) for v in (proc/'environ').read_bytes().decode().split('\0') if '=' in v)
            command = (proc/'cmdline').read_bytes().split(b'\0')
            if b'/usr/local/bin/tzx-screen' in command and b'--daemon' in command:
                os.kill(int(proc.name), signal.SIGTERM)
        except (OSError, ValueError):
            continue
    assert values and values['DISPLAY'] == ':0'
    environment = [k+'='+values[k] for k in ('DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR') if k in values]
    with Path('/var/log/tzx-screen-orientation.log').open('ab') as log:
        process = subprocess.Popen(['runuser', '-u', 'debian', '--', 'env', *environment,
                                    '/usr/local/bin/tzx-screen', '--daemon'],
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    time.sleep(3)
    assert process.poll() is None


if a.operation == 'install':
    state = json.loads(STATE.read_text())
    assert state['profile'] == 'screen-functions-3-doublebuffer'
    assert state['state'] == 'doublebuffer_manual_trial_running'
    assert not BACKUP.exists()
    for name, item in state['files'].items():
        assert hashlib.sha256((Path('/')/name).read_bytes()).hexdigest() == item['sha256'], name
    assert hashlib.sha256(APP.read_bytes()).hexdigest() == OLD
    package = Path('/home/debian/screen-runtime-doublebuffer-settings.tar.gz').read_bytes()
    manifest_bytes = Path('/home/debian/screen-runtime-doublebuffer-settings-FILES.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    assert hashlib.sha256(package).hexdigest() == manifest['package_sha256']
    assert set(manifest['files']) == set(state['files'])
    changed = {name for name in state['files'] if state['files'][name]['sha256'] != manifest['files'][name]['sha256']}
    assert changed == {'usr/local/bin/tzx-screen'}
    with tarfile.open(fileobj=io.BytesIO(package), mode='r:gz') as archive:
        assert set(archive.getnames()) == set(manifest['files'])
        files = {}
        for entry in archive.getmembers():
            assert entry.isfile() and not entry.name.startswith('/') and '..' not in Path(entry.name).parts
            data = archive.extractfile(entry).read()
            assert hashlib.sha256(data).hexdigest() == manifest['files'][entry.name]['sha256']
            files[entry.name] = data
    BACKUP.mkdir(parents=True)
    atomic(BACKUP/'before-state.json', STATE.read_bytes())
    atomic(BACKUP/'before-app.py', APP.read_bytes())
    atomic(BACKUP/'before-concurrency.json', (ROOT/'screen-settings-concurrency.json').read_bytes())
    atomic(BACKUP/'package.tar.gz', package)
    atomic(BACKUP/'FILES.json', manifest_bytes)
    atomic(BACKUP/'installer.py', Path(__file__).read_bytes())
    atomic(APP, files['usr/local/bin/tzx-screen'], 0o755)
    state.update(files=manifest['files'], package_sha256=manifest['package_sha256'], settings_save_revision=2)
    atomic(STATE, (json.dumps(state, indent=2)+'\n').encode())
else:
    before = json.loads((BACKUP/'before-state.json').read_text())
    current = json.loads((BACKUP/'FILES.json').read_text())
    assert hashlib.sha256(APP.read_bytes()).hexdigest() == current['files']['usr/local/bin/tzx-screen']['sha256']
    data = (BACKUP/'before-app.py').read_bytes()
    assert hashlib.sha256(data).hexdigest() == OLD
    atomic(APP, data, 0o755)
    atomic(STATE, (BACKUP/'before-state.json').read_bytes())
restart_daemon()
os.sync()
print('TZX_SCREEN_SETTINGS_SAVE_REVISION', a.operation, flush=True)
