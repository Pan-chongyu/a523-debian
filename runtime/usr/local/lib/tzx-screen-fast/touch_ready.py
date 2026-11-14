"""Separate the verified touch supply milestone from completed input startup."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == Path('/etc/tzx/device-cid').read_text().strip()
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert sys.argv[1:] in (['rails'], ['input'], ['wait'])
operation = sys.argv[1]
rail = Path('/run/tzx-touch-rail-ready.json')
ready = Path('/run/tzx-touch-input-ready.json')

def record(path, phase):
    temporary = path.with_suffix('.tmp')
    value = dict(boot_id=boot, phase=phase, monotonic_s=time.monotonic())
    temporary.write_text(json.dumps(value)+'\n')
    temporary.chmod(0o644)
    temporary.replace(path)
    return value

def input_bound():
    path = Path('/sys/bus/i2c/devices/1-0040/driver')
    return path.is_symlink() and path.resolve().name == 'tzx-gsl3670' and any(
        p.read_text().strip() == 'TZX GSL3670 candidate'
        for p in Path('/sys/class/input').glob('input*/name'))

if operation == 'rails':
    assert 'NOTIFY_SOCKET' in os.environ
    assert Path('/run/tzx-touch-runtime-cldo2').read_text().strip() in ('0xd5', '0xd7')
    assert subprocess.check_output(['i2cget', '-y', '0', '0x34', '0x91'], text=True, timeout=3).strip() == '0xd7'
    assert not Path('/sys/module/tzx_touch_runtime').exists()
    value = record(rail, 'CLDO2-enabled-before-original-touch-settle')
    subprocess.run(['systemd-notify', '--ready', '--status=Touch supply ready; loading firmware'], check=True, timeout=3)
    print('TZX_TOUCH_SUPPLY_READY_DISPLAY_MAY_START', json.dumps(value), flush=True)
elif operation == 'input':
    assert rail.is_file() and json.loads(rail.read_text())['boot_id'] == boot
    assert input_bound()
    value = record(ready, 'firmware-validated-and-input-bound')
    subprocess.run(['systemd-notify', '--status=Touch firmware and input ready'], check=True, timeout=3)
    print('TZX_TOUCH_FULL_INPUT_READY', json.dumps(value), flush=True)
else:
    until = time.monotonic()+24
    while time.monotonic() < until:
        props = dict(v.split('=', 1) for v in subprocess.check_output(
            ['systemctl', 'show', 'tzx-touch', '-p', 'ActiveState', '-p', 'SubState'],
            text=True, timeout=3).splitlines())
        assert props['ActiveState'] not in ('failed', 'inactive'), props
        if ready.is_file() and json.loads(ready.read_text())['boot_id'] == boot and input_bound() and props['SubState'] == 'exited':
            print('TZX_TOUCH_COMPLETE_BEFORE_DESKTOP', ready.read_text().strip(), flush=True)
            break
        time.sleep(.1)
    else:
        raise RuntimeError('Touch firmware completion did not become ready')
