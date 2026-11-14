"""Exercise the real DRM WAIT_VBLANK ioctl and its DPMS lifetime."""
import ctypes
import errno
import json
import os
from pathlib import Path
import subprocess
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/module/tzx_display/parameters/screen_revision').read_text().strip() in ('screen-functions-2-vblank', 'screen-functions-3-doublebuffer', 'screen-functions-4-standby', 'screen-functions-5-poweron')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
env = dict(os.environ, DISPLAY=':0', XAUTHORITY='/run/lightdm/root/:0')


class Request(ctypes.Structure):
    _fields_ = [('type', ctypes.c_uint), ('sequence', ctypes.c_uint), ('signal', ctypes.c_ulong)]


class Reply(ctypes.Structure):
    _fields_ = [('type', ctypes.c_uint), ('sequence', ctypes.c_uint),
                ('sec', ctypes.c_long), ('usec', ctypes.c_long)]


class VBlank(ctypes.Union):
    _fields_ = [('request', Request), ('reply', Reply)]


drm = ctypes.CDLL('libdrm.so.2', use_errno=True)
drm.drmWaitVBlank.argtypes = [ctypes.c_int, ctypes.POINTER(VBlank)]
drm.drmWaitVBlank.restype = ctypes.c_int
assert ctypes.sizeof(VBlank) == 24
fd = os.open('/dev/dri/by-path/platform-tzx-de-scanout-card', os.O_RDWR | os.O_CLOEXEC)
counter = Path('/sys/module/tzx_display/parameters/screen_vblank_events')


def sample():
    before = int(counter.read_text())
    values = []
    start = time.monotonic()
    for i in range(120):
        v = VBlank()
        v.request.type = 1  # DRM_VBLANK_RELATIVE, CRTC 0, one real frame.
        v.request.sequence = 1
        ret = drm.drmWaitVBlank(fd, ctypes.byref(v))
        assert ret == 0, (ret, ctypes.get_errno(), errno.errorcode.get(ctypes.get_errno()))
        values.append((v.reply.sequence, v.reply.sec * 1000000 + v.reply.usec))
    elapsed = time.monotonic() - start
    deltas = [(b[1]-a[1])/(b[0]-a[0]) for a, b in zip(values, values[1:]) if b[0] > a[0]]
    assert len(deltas) == 119 and all(15000 < v < 17000 for v in deltas), deltas
    assert 1.5 < elapsed < 6.0, elapsed
    hardware_events = int(counter.read_text()) - before
    assert hardware_events >= 119, hardware_events
    return {'waits': 120, 'elapsed_seconds': elapsed, 'hardware_irq_delta': hardware_events,
            'first_sequence': values[0][0], 'last_sequence': values[-1][0],
            'per_frame_us_min': min(deltas), 'per_frame_us_max': max(deltas)}


tests = []
try:
    for cycle in range(3):
        subprocess.run(['xset', 'dpms', 'force', 'on'], env=env, check=True, timeout=8)
        time.sleep(.4)
        tests.append(dict(cycle=cycle, **sample()))
        subprocess.run(['xset', '+dpms'], env=env, check=True, timeout=8)
        subprocess.run(['xset', 'dpms', 'force', 'off'], env=env, check=True, timeout=8)
        time.sleep(.7)
        assert int(Path('/sys/class/backlight/tzx-panel/actual_brightness').read_text()) == 0
finally:
    subprocess.run(['xset', 'dpms', 'force', 'on'], env=env, check=True, timeout=8)
    os.close(fd)
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert not subprocess.check_output(['systemctl', '--failed', '--no-legend'], text=True).strip()
result = {'boot_id': boot, 'result': 'PASS', 'cycles': tests,
          'DPMS_recovered': True, 'hardware_source': 'DSI1 VIDEO_VBLK GIC SPI95'}
path = Path('/var/lib/tzx/screen-vblank-test.json')
with path.open('w') as f:
    json.dump(result, f, indent=2)
    f.write('\n')
    f.flush()
    os.fsync(f.fileno())
print('TZX_SCREEN_HARDWARE_DRM_VBLANK_DPMS_PASS', json.dumps(result), flush=True)
