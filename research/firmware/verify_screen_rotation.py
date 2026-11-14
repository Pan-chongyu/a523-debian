"""Validate all four X11 orientations and the actual touch transformation."""
import json
import os
from pathlib import Path
import re
import subprocess
import time

assert os.geteuid() == 0
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
revision = Path('/sys/module/tzx_display/parameters/screen_revision').read_text().strip()
assert revision in ('screen-functions-1', 'screen-functions-2-vblank', 'screen-functions-3-doublebuffer', 'screen-functions-4-standby', 'screen-functions-5-poweron')
env = None
for proc in Path('/proc').glob('[0-9]*'):
    try:
        if proc.stat().st_uid == 1000 and (proc/'comm').read_text().strip() == 'xfce4-session':
            values = dict(v.split('=', 1) for v in (proc/'environ').read_bytes().decode().split('\0') if '=' in v)
            env = {k: values[k] for k in ('DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR') if k in values}
            break
    except (OSError, ValueError):
        continue
assert env and env.get('DISPLAY') == ':0'
root_env = dict(os.environ, DISPLAY=':0', XAUTHORITY='/run/lightdm/root/:0')


def x(*cmd):
    return subprocess.check_output(cmd, env=root_env, text=True, stderr=subprocess.STDOUT, timeout=15)


def app(*cmd):
    result = subprocess.run(['runuser', '-u', 'debian', '--', 'env',
                             *(k+'='+v for k, v in env.items()),
                             '/usr/local/bin/tzx-screen', *cmd],
                            text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=20)
    assert result.returncode == 0, (cmd, result.returncode, result.stdout)
    return result.stdout


matrices = {'normal': (1, 0, 0, 0, 1, 0, 0, 0, 1),
            'left': (0, -1, 1, 1, 0, 0, 0, 0, 1),
            'inverted': (-1, 0, 1, 0, -1, 1, 0, 0, 1),
            'right': (0, 1, 0, -1, 0, 1, 0, 0, 1)}
tests = []
before = x('xrandr', '--query')
head = next(line.split('(')[0] for line in before.splitlines() if line.startswith('DSI-1 connected'))
original = next((r for r in ('left', 'right', 'inverted') if r in head.split()), 'normal')
original_brightness = int(Path('/sys/class/backlight/tzx-panel/brightness').read_text())
try:
    for cycle in range(2):
        for rotation, matrix in matrices.items():
            app('--rotate', rotation)
            time.sleep(1)
            query = x('xrandr', '--query')
            expected = (800, 1280) if rotation in ('normal', 'inverted') else (1280, 800)
            actual = re.search(r'current (\d+) x (\d+)', query)
            assert actual and tuple(map(int, actual.groups())) == expected, query
            properties = x('xinput', 'list-props', 'TZX GSL3670 candidate')
            values = next(line.split(':', 1)[1] for line in properties.splitlines()
                          if 'Coordinate Transformation Matrix (' in line)
            actual_matrix = tuple(float(v.strip()) for v in values.split(','))
            assert actual_matrix == matrix, properties
            item = {'cycle': cycle, 'rotation': rotation, 'desktop': expected,
                    'touch_matrix': actual_matrix, 'result': 'PASS'}
            tests.append(item)
            print(json.dumps(item), flush=True)
    # An ordinary unprivileged desktop process can use the logind backlight API.
    app('--set-brightness', '35')
    assert int(Path('/sys/class/backlight/tzx-panel/actual_brightness').read_text()) == 35
finally:
    app('--rotate', original)
    app('--set-brightness', str(max(1, original_brightness)))
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert 'Mali-G57' in x('glxinfo', '-B')
assert not subprocess.check_output(['systemctl', '--failed', '--no-legend'], text=True).strip()
record = {'boot_id': boot, 'tests': tests, 'original_rotation_restored': original,
          'unprivileged_logind_brightness': 'PASS', 'result': 'PASS'}
path = Path('/var/lib/tzx/screen-rotation-test.json')
with path.open('w') as f:
    json.dump(record, f, indent=2)
    f.write('\n')
    f.flush()
    os.fsync(f.fileno())
print('TZX_SCREEN_FOUR_ORIENTATIONS_AND_TOUCH_MATRIX_PASS', flush=True)
