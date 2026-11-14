"""Verify actual display autostart and persistence after a normal reboot."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

assert os.geteuid() == 0
ROOT = Path('/var/lib/tzx')
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
intent = json.loads((ROOT/'screen-reboot-intent.json').read_text())
assert BOOT != intent['previous_boot_id']
state = json.loads((ROOT/'screen-installed.json').read_text())
assert state['state'] == 'manual_display_and_actual_autostart_verified'
assert state['verified_boot_id'] == BOOT
for name, item in state['files'].items():
    assert hashlib.sha256((Path('/')/name).read_bytes()).hexdigest() == item['sha256'], name
env = dict(os.environ, DISPLAY=':0', XAUTHORITY='/run/lightdm/root/:0')
rotation = intent['orientation']
for attempt in range(60):
    query = subprocess.check_output(['xrandr', '--query'], env=env, text=True, timeout=10)
    line = next(line.split('(')[0].split() for line in query.splitlines() if line.startswith('DSI-1 connected'))
    actual = next((r for r in ('left', 'right', 'inverted') if r in line), 'normal')
    if actual == rotation:
        break
    time.sleep(1)
else:
    raise RuntimeError('Saved desktop rotation was not restored')
brightness = int(Path('/sys/class/backlight/tzx-panel/brightness').read_text())
assert brightness == intent['brightness'], (brightness, intent)
actual = int(Path('/sys/class/backlight/tzx-panel/actual_brightness').read_text())
assert actual == brightness
matrices = {'normal': (1, 0, 0, 0, 1, 0, 0, 0, 1),
            'left': (0, -1, 1, 1, 0, 0, 0, 0, 1),
            'right': (0, 1, 0, -1, 0, 1, 0, 0, 1),
            'inverted': (-1, 0, 1, 0, -1, 1, 0, 0, 1)}
props = subprocess.check_output(['xinput', 'list-props', 'TZX GSL3670 candidate'], env=env, text=True, timeout=10)
value = next(line.split(':', 1)[1] for line in props.splitlines() if 'Coordinate Transformation Matrix (' in line)
matrix = tuple(float(v.strip()) for v in value.split(','))
assert matrix == matrices[rotation], matrix
assert 'Mali-G57' in subprocess.check_output(['glxinfo', '-B'], env=env, text=True, timeout=15)
assert not (ROOT/'screen-boot-pending.json').exists()
assert not subprocess.check_output(['systemctl', '--failed', '--no-legend'], text=True).strip()
state['brightness_persistence'] = 'actual_reboot_verified'
state['persistence_verified_boot_id'] = BOOT
state['persistence_proof'] = {'brightness': brightness, 'orientation': rotation,
                             'touch_matrix': matrix, 'previous_boot_id': intent['previous_boot_id']}
tmp = ROOT/'screen-installed.json.new'
with tmp.open('w') as f:
    json.dump(state, f, indent=2)
    f.write('\n')
    os.fchmod(f.fileno(), 0o600)
    f.flush()
    os.fsync(f.fileno())
tmp.replace(ROOT/'screen-installed.json')
fd = os.open(ROOT, os.O_DIRECTORY)
os.fsync(fd)
os.close(fd)
print('TZX_SCREEN_ACTUAL_REBOOT_BRIGHTNESS_ROTATION_TOUCH_GPU_PASS', json.dumps(state['persistence_proof']), flush=True)
