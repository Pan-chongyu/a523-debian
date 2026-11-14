"""Apply bounded source-selection diagnostics to the module-owned video path.

The module's unload callback restores every affected register. The wrapper's
systemd timer must still be armed; no new clocks, rails or GPIO are touched.
"""
import fcntl
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
params = Path('/sys/module/tzx_dsi_probe/parameters')
for name in ('video', 'hold', 'hs_clock', 'probe_panel'):
    assert (params / name).read_text().strip() == 'Y', name
assert subprocess.run(['systemctl', 'is-active', '--quiet', 'tzx-display-test-timeout.timer']).returncode == 0
action = sys.argv[1]
assert action in ('bist', 'hv', 'cpu', 'command', 'hsc')
with open('/run/tzx-dsi-live.lock', 'w') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
    host = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x05508000)
    tcon = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x05502000)
    phy = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x05509000)
    def get(memory, off):
        return struct.unpack_from('<I', memory, off)[0]
    def put(memory, off, value):
        struct.pack_into('<I', memory, off, value)
    put(host, 0x10, 3 << 16)
    if action == 'bist':
        put(host, 0x2f8, (1 << 28) | 0xffffff)
    elif action in ('hv', 'cpu'):
        put(tcon, 0, 0)
        ctl = get(tcon, 0x40) & ~(1 << 24)
        if action == 'cpu':
            ctl |= 1 << 24
        put(tcon, 0x40, ctl)
        put(tcon, 0, 1 << 31)
    elif action == 'command':
        put(host, 0x14, 0)
    jump = 6 | (3 << 24) | (7 << 12) | (6 << 28) | (15 << 20)
    if action == 'hsc':
        # Match mainline's separate HSC -> END, then HSD start. Status
        # reads include a DLY instruction that can return the clock to LP.
        put(host, 0x20, 0x1f)
        put(host, 0x48, 2 | (15 << 8))
        put(host, 0x10, (3 << 16) | 1)
        deadline = time.monotonic() + 0.04
        while get(host, 0x10) & 1:
            if time.monotonic() > deadline:
                put(host, 0x10, 3 << 16)
                raise TimeoutError('HS clock instruction timeout')
            time.sleep(0.0001)
        print(json.dumps({'action': 'hsc-only', 'phy': f'{get(phy, 0xe0):08x}'}), flush=True)
        time.sleep(0.001)
        put(host, 0x20, 0x0f)
    put(host, 0x48, jump)
    put(host, 0x10, (3 << 16) | 1)
    time.sleep(0.1)
    print(json.dumps({'action': action,
        'line': get(host, 0x2e0), 'inst': get(host, 0x2f0),
        'fifo': get(host, 0x2f4), 'bist': get(host, 0x2f8),
        'tcon': get(tcon, 0xfc), 'phy': f'{get(phy, 0xe0):08x}'}))
    phy.close()
    tcon.close()
    host.close()
    os.close(fd)
