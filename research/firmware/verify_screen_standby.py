"""Verify KMS DPMS actually stops DSI video and toggles panel DCS sleep state."""
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import time

assert os.geteuid() == 0
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
params = Path('/sys/module/tzx_display/parameters')
assert (params/'screen_revision').read_text().strip() in ('screen-functions-4-standby', 'screen-functions-5-poweron')
env = dict(os.environ, DISPLAY=':0', XAUTHORITY='/run/lightdm/root/:0')
bl = Path('/sys/class/backlight/tzx-panel')


def x(*command):
    return subprocess.check_output(command, env=env, text=True, stderr=subprocess.STDOUT, timeout=20)


def sample():
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    try:
        with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x05508000) as regs:
            busy = struct.unpack_from('<I', regs, 0x10)[0] & 1
    finally:
        os.close(fd)
    return {'sleeping': (params/'screen_panel_sleeping').read_text().strip() == 'Y',
            'sleep_count': int((params/'screen_panel_sleeps').read_text()),
            'wake_count': int((params/'screen_panel_wakes').read_text()),
            'errors': int((params/'screen_panel_errors').read_text()),
            'scanout_errors': int((params/'screen_buffer_errors').read_text()),
            'sleep_status': int((params/'screen_sleep_status').read_text()),
            'wake_status': int((params/'screen_wake_status').read_text()),
            'DSI_instruction_running': busy, 'actual_brightness': int((bl/'actual_brightness').read_text())}


before = sample()
settings = x('xset', 'q')
assert 'DPMS is Enabled' in settings
samples = []
try:
    for cycle in range(5):
        x('xset', 'dpms', 'force', 'off')
        time.sleep(.7)
        off = sample()
        assert off['sleeping'] and off['DSI_instruction_running'] == 0 and off['actual_brightness'] == 0, off
        assert off['sleep_status'] >= 0 and not off['sleep_status'] & 0x10, off
        assert off['errors'] == 0 and off['scanout_errors'] == 0, off
        x('xset', 'dpms', 'force', 'on')
        time.sleep(.7)
        on = sample()
        assert not on['sleeping'] and on['DSI_instruction_running'] == 1 and on['actual_brightness'] > 0, on
        assert on['wake_status'] >= 0 and on['wake_status'] & 0x10, on
        assert on['errors'] == 0 and on['scanout_errors'] == 0, on
        item = {'cycle': cycle, 'off': off, 'on': on}
        samples.append(item)
        print(json.dumps(item), flush=True)
finally:
    x('xset', 'dpms', 'force', 'on')
after = sample()
assert after['sleep_count'] >= before['sleep_count']+5
assert after['wake_count'] >= before['wake_count']+5
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
assert 'Mali-G57' in x('glxinfo', '-B')
proof = {'boot_id': boot, 'result': 'PASS', 'samples': samples,
         'qualification': 'DSI host stopped, backlight off, DCS sleep-out bit toggles and accelerated desktop resumes',
         'limitation': 'bias and panel supply remain powered; not full rail gating or system suspend'}
Path('/var/lib/tzx/screen-standby-test.json').write_text(json.dumps(proof, indent=2)+'\n')
print('TZX_SCREEN_DCS_SLEEP_VIDEO_STOP_AND_WAKE_PASS', flush=True)
