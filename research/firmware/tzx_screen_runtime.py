"""Guard the board display revision and retain the qualified original fallback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/usr/local/lib/tzx-screen')
STATE = Path('/var/lib/tzx/screen-installed.json')
QUALIFIED = Path('/var/lib/tzx/screen-qualified.json')
PENDING = Path('/var/lib/tzx/screen-boot-pending.json')
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
GPU = '/usr/local/lib/tzx-dram-gpu/runtime.py'
MODULE_SHA = '4c565e31c3ad5bbef6900b95a79bee651026881a0421f2f0049f1f9135bd5491'
p = argparse.ArgumentParser()
p.add_argument('operation', choices=('start', 'stop', 'health'))
p.add_argument('--trial', action='store_true')
a = p.parse_args()
assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'


def run(*command, timeout=55, **kwargs):
    return subprocess.run(command, check=True, timeout=timeout, **kwargs)


def atomic(path, value):
    tmp = path.with_name(path.name+'.new')
    with tmp.open('w') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
        os.fchmod(f.fileno(), 0o600)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)


def base(operation):
    run('python3', GPU, 'display-'+operation)


if a.operation == 'stop':
    # The generic backlight unit may stop after this platform device vanishes.
    # Save the requested value while its sysfs files are still present.
    if Path('/sys/class/backlight/tzx-panel/brightness').exists():
        run('/usr/lib/systemd/systemd-backlight', 'save', 'backlight:tzx-panel')
    # Both display revisions use the same reversible CLDO4 rail transaction.
    base('stop')
elif a.operation == 'start':
    qualified = a.trial or QUALIFIED.exists()
    old_pending = PENDING.exists() and json.loads(PENDING.read_text())['boot_id'] != BOOT
    if not qualified or old_pending or not Path('/var/lib/tzx/gpu-qualified').exists():
        if old_pending:
            atomic(Path('/var/lib/tzx/screen-fallback.json'),
                   {'boot_id': BOOT, 'reason': 'Previous screen boot did not complete',
                    'previous': json.loads(PENDING.read_text())})
        base('start')
        print('TZX_SCREEN_ORIGINAL_DISPLAY_FALLBACK', flush=True)
    else:
        run('python3', GPU, 'guard')
        assert hashlib.sha256((ROOT/'tzx_display.ko').read_bytes()).hexdigest() == MODULE_SHA
        original = Path('/usr/local/lib/tzx-dram-gpu/display-runtime').read_bytes()
        assert hashlib.sha256(original).hexdigest() == '478024b8afe405e550e36ed98d38d6b5794049d1c65bf135effee60637ae940f'
        old = b'insmod /usr/local/lib/tzx-dram-gpu/tzx_display.ko'
        assert original.count(old) == 1
        script = original.replace(old, b'insmod /usr/local/lib/tzx-screen/tzx_display.ko')
        atomic(PENDING, {'boot_id': BOOT, 'module_sha256': MODULE_SHA, 'trial': a.trial})
        run('/bin/sh', '-c', script.decode(), 'screen-display-runtime', 'start')
        assert Path('/sys/module/tzx_display/parameters/screen_revision').read_text().strip() == 'screen-functions-1'
        print('TZX_SCREEN_CANDIDATE_READY', flush=True)
elif a.operation == 'health':
    revision = Path('/sys/module/tzx_display/parameters/screen_revision')
    if not revision.exists():
        assert not PENDING.exists() or json.loads(PENDING.read_text())['boot_id'] != BOOT
        print('TZX_SCREEN_HEALTH_ORIGINAL_FALLBACK', flush=True)
    else:
        assert revision.read_text().strip() == 'screen-functions-1'
        assert PENDING.exists() and json.loads(PENDING.read_text())['boot_id'] == BOOT
        env = dict(os.environ, DISPLAY=':0', XAUTHORITY='/run/lightdm/root/:0')
        for attempt in range(20):
            result = subprocess.run(['xrandr', '--query'], env=env, capture_output=True, text=True, timeout=8)
            if result.returncode == 0 and 'maximum 1280 x 1280' in result.stdout:
                break
            time.sleep(1)
        else:
            raise RuntimeError('Desktop did not expose the rotation buffer range')
        gpu_health = json.loads(Path('/var/lib/tzx/dram-gpu-boot-health.json').read_text())
        assert gpu_health['boot_id'] == BOOT and gpu_health['status'] == 'PASS'
        assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
        atomic(Path('/var/lib/tzx/screen-boot-health.json'),
               {'boot_id': BOOT, 'result': 'PASS', 'revision': 'screen-functions-1',
                'module_sha256': MODULE_SHA, 'GPU': 'Mali-G57', 'xrandr': result.stdout})
        PENDING.unlink()
        if STATE.exists():
            state = json.loads(STATE.read_text())
            if state['installed_boot_id'] != BOOT:
                state['state'] = 'manual_display_and_actual_autostart_verified'
                state['verified_boot_id'] = BOOT
                atomic(STATE, state)
        print('TZX_SCREEN_BOOT_HEALTH_PASS', flush=True)
