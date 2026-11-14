"""Observe alternating RCQ scanout addresses while X11 presents animation."""
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import time

assert os.geteuid() == 0
assert Path('/sys/module/tzx_display/parameters/screen_revision').read_text().strip() in ('screen-functions-3-doublebuffer', 'screen-functions-4-standby', 'screen-functions-5-poweron')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
params = Path('/sys/module/tzx_display/parameters')
before = int((params/'screen_buffer_commits').read_text())
env = dict(os.environ, DISPLAY=':0', XAUTHORITY='/run/lightdm/root/:0')
log = Path('/home/debian/screen-doublebuffer-animation.log')
addresses = set()
samples = []
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
try:
    with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x051c1000) as regs, log.open('w') as output:
        process = subprocess.Popen(['glmark2-es2', '--size', '600x480', '-b', 'build:duration=8',
                                    '-b', 'texture:duration=8'], env=env, stdout=output, stderr=subprocess.STDOUT)
        start = time.monotonic()
        try:
            while process.poll() is None:
                address = struct.unpack_from('<I', regs, 0x10)[0]
                addresses.add(address)
                count = int((params/'screen_buffer_commits').read_text())
                assert int((params/'screen_buffer_errors').read_text()) == 0
                samples.append({'seconds': round(time.monotonic()-start, 3),
                                'scanout_address': hex(address), 'commits': count})
                assert len(addresses) <= 2 and time.monotonic()-start < 45
                for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
                    assert 0 < int((zone/'temp').read_text()) < 75000
                time.sleep(.013)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
finally:
    os.close(fd)
assert process.returncode == 0, log.read_text()
assert 'Mali-G57' in log.read_text() and 'glmark2 Score:' in log.read_text()
assert len(addresses) == 2 and all(a < 0x100000000 for a in addresses), addresses
commits = int((params/'screen_buffer_commits').read_text())-before
assert commits > 100, commits
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
result = {'boot_id': boot, 'result': 'PASS', 'addresses': [hex(a) for a in sorted(addresses)],
          'commits': commits, 'samples': samples, 'scanout_errors': 0,
          'qualification': 'actual DE address alternation under accelerated X11; subjective visual check separate'}
path = Path('/var/lib/tzx/screen-doublebuffer-test.json')
with path.open('w') as f:
    json.dump(result, f, indent=2)
    f.write('\n')
    f.flush()
    os.fsync(f.fileno())
print('TZX_SCREEN_DUAL_DMA_RCQ_ADDRESS_ANIMATION_PASS', json.dumps({k: v for k, v in result.items() if k != 'samples'}), flush=True)
