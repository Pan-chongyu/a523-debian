"""Read-only snapshots and line-wrap sampling during the held video test."""
import fcntl
import json
import mmap
import os
from pathlib import Path
import struct
import time

assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
params = Path('/sys/module/tzx_dsi_probe/parameters')
assert (params / 'video').read_text().strip() == 'Y'
assert (params / 'hold').read_text().strip() == 'Y'
with open('/run/tzx-dsi-live.lock', 'w') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    host = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x05508000)
    tcon = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x05502000)
    phy = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x05509000)
    def get(memory, off):
        return struct.unpack_from('<I', memory, off)[0]
    output = {'dsi': {}, 'tcon': {}, 'phy': {}, 'samples': []}
    for off in (0, 4, 0xc, 0x10, 0x14, 0x18, 0x1c, 0x48, 0x7c, 0x80, 0x90, 0xfc, 0x2e0, 0x2e4, 0x2f0, 0x2f4, 0x2f8):
        output['dsi'][f'{off:03x}'] = f'{get(host, off):08x}'
    for off in (0, 4, 0x3c, 0x40, 0x44, 0x48, 0x60, 0xf8, 0xfc, 0x160, 0x164, 0x168):
        output['tcon'][f'{off:03x}'] = f'{get(tcon, off):08x}'
    for off in (0, 4, 0x10, 0x14, 0x18, 0x20, 0x4c, 0x50, 0x54, 0x58, 0x5c, 0xe0, 0xe4, 0xe8, 0xec, 0x104, 0x108, 0x110, 0x114):
        output['phy'][f'{off:03x}'] = f'{get(phy, off):08x}'
    started = time.monotonic()
    last, wraps, distinct = None, 0, set()
    while time.monotonic() - started < 2:
        line = get(host, 0x2e0) & 8191
        if last is not None and line < last:
            wraps += 1
        last = line
        distinct.add(line)
        if len(output['samples']) < 20:
            output['samples'].append({'line': line, 'fifo': get(host, 0x2f4), 'inst': get(host, 0x2f0), 'tcon': get(tcon, 0xfc)})
        time.sleep(0.001)
    output['elapsed'] = time.monotonic() - started
    output['line_wraps'] = wraps
    output['distinct_lines'] = len(distinct)
    output['line_range'] = [min(distinct), max(distinct)]
    print(json.dumps(output, indent=2))
    tcon.close()
    phy.close()
    host.close()
    os.close(fd)
