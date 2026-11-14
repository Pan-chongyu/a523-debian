#!/usr/bin/python3
"""Set landscape before LightDM shows its greeter or starts a user session."""
import json
import os
from pathlib import Path
import re
import subprocess


def command(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=12)


def rotation(query):
    line = next(row.split('(')[0].split() for row in query.splitlines() if row.startswith('DSI-1 connected'))
    return next((value for value in ('left', 'right', 'inverted') if value in line), 'normal')


boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
result = {'boot_id': boot, 'stage': 'before_greeter_and_session', 'result': 'PASS'}
try:
    result['initial_query'] = command('xrandr', '--query')
    command('xrandr', '--output', 'DSI-1', '--rotate', 'right', '--primary')
    result['query'] = command('xrandr', '--query')
    assert rotation(result['query']) == 'right'
    assert 'current 1280 x 800' in result['query']
    result['touch_properties'] = command('xinput', 'list-props', 'TZX GSL3670 candidate')
    command('xinput', 'set-prop', 'TZX GSL3670 candidate', 'Coordinate Transformation Matrix',
            '0', '1', '0', '-1', '0', '1', '0', '0', '1')
    result['touch_properties'] = command('xinput', 'list-props', 'TZX GSL3670 candidate')
    matrix = next(row.split(':', 1)[1] for row in result['touch_properties'].splitlines()
                  if 'Coordinate Transformation Matrix (' in row)
    assert tuple(float(v.strip()) for v in matrix.split(',')) == (0, 1, 0, -1, 0, 1, 0, 0, 1)
    result['fbcon_rotate'] = Path('/sys/class/graphics/fbcon/rotate').read_text().strip()
    result['kernel_rotation_enabled'] = Path('/boot/kernel.config').read_text().find(
        'CONFIG_FRAMEBUFFER_CONSOLE_ROTATION=y') >= 0
except (OSError, AssertionError, StopIteration, subprocess.SubprocessError) as error:
    # Keep a usable greeter even if the diagnostic display falls back.
    result.update(result='FAIL', error=str(error))
path = Path('/var/lib/tzx/screen-display-setup.json')
temp = path.with_suffix('.new')
with temp.open('w') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
    stream.flush()
    os.fsync(stream.fileno())
temp.replace(path)
print('TZX_SCREEN_BEFORE_GREETER', json.dumps(result), flush=True)
