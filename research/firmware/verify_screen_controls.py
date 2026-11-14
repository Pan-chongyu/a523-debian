"""Exercise the standard backlight and X11 DPMS, checking physical PWM state."""
import argparse
import json
import mmap
import os
from pathlib import Path
import re
import struct
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument('--visible', action='store_true')
a = p.parse_args()
assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
bl = Path('/sys/class/backlight/tzx-panel')
env = dict(os.environ, DISPLAY=':0', XAUTHORITY='/run/lightdm/root/:0')


def x(*cmd):
    return subprocess.check_output(cmd, env=env, text=True, timeout=12)


def pwm_state():
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    try:
        with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x02000000) as view:
            return {hex(i): struct.unpack_from('<I', view, i)[0]
                    for i in (0xc20, 0xc40, 0xc80, 0xd00, 0xd04)}
    finally:
        os.close(fd)


def sample(label, brightness=None, enabled=None):
    record = {'label': label, 'brightness': int((bl/'brightness').read_text()),
              'actual_brightness': int((bl/'actual_brightness').read_text()),
              'bl_power': int((bl/'bl_power').read_text()), 'pwm': pwm_state()}
    if brightness is not None:
        assert record['brightness'] == brightness, record
        assert record['pwm']['0xd04'] & 0xffff == brightness * 480 // 100, record
    if enabled is not None:
        assert bool(record['pwm']['0xc80'] & 1) == enabled, record
        if Path('/sys/module/tzx_display/parameters/screen_revision').exists():
            expected = record['brightness'] if enabled else 0
            assert record['actual_brightness'] == expected, record
    print(json.dumps(record), flush=True)
    samples.append(record)


saved_brightness = (bl/'brightness').read_text()
saved_power = (bl/'bl_power').read_text()
settings = x('xset', 'q')
timeouts = re.search(r'Standby:\s+(\d+)\s+Suspend:\s+(\d+)\s+Off:\s+(\d+)', settings)
was_enabled = 'DPMS is Enabled' in settings
samples = []
try:
    (bl/'bl_power').write_text('0\n')
    x('xset', '+dpms')
    x('xset', 'dpms', '0', '0', '0')
    x('xset', 'dpms', 'force', 'on')
    for level in (10, 35, 70, 20, 0, 20):
        (bl/'brightness').write_text(str(level)+'\n')
        time.sleep(5 if a.visible else 0.3)
        sample('brightness-'+str(level), level, bool(level))
    x('xset', 'dpms', 'force', 'off')
    time.sleep(5 if a.visible else 0.5)
    sample('X11-DPMS-off', enabled=False)
    x('xset', 'dpms', 'force', 'on')
    time.sleep(5 if a.visible else 0.5)
    sample('X11-DPMS-on', 20, True)
finally:
    x('xset', 'dpms', 'force', 'on')
    (bl/'brightness').write_text(saved_brightness)
    (bl/'bl_power').write_text(saved_power)
    if timeouts:
        x('xset', 'dpms', *timeouts.groups())
    if not was_enabled:
        x('xset', '-dpms')
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
result = {'boot_id': boot, 'standard_backlight_and_DPMS': 'PASS', 'samples': samples,
          'original_brightness_restored': int(saved_brightness), 'result': 'PASS'}
Path('/var/lib/tzx/screen-controls-test.json').write_text(json.dumps(result, indent=2)+'\n')
print('TZX_SCREEN_BACKLIGHT_DPMS_TEST_PASS', flush=True)
