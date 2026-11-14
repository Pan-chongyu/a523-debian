"""Bounded 396 MHz external-clock comparison; restore mux/divider on exit.

Only run with the exact tablet's held video diagnostic and armed cleanup.
The ordinary 1188 MHz video PLL is divided by three, without retuning it.
The mismatched TCON pixel clock makes this a transport test, not a mode.
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
    assert (params / name).read_text().strip() == 'Y'
assert subprocess.run(['systemctl', 'is-active', '--quiet', 'tzx-display-test-timeout.timer']).returncode == 0
with open('/run/tzx-dsi-live.lock', 'w') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
    maps = [mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=address)
            for address in (0x05508000, 0x05502000, 0x05509000, 0x05500000, 0x02001000)]
    host, tcon, phy, top, ccu = maps
    def get(memory, offset):
        return struct.unpack_from('<I', memory, offset)[0]
    def put(memory, offset, value):
        struct.pack_into('<I', memory, offset, value)
    internal = len(sys.argv) > 1 and sys.argv[1] == 'internal'
    original = {'ccu': get(ccu, 0xb70), 'top': get(top, 0xc),
                'tcon': get(tcon, 0), 'lp11': get(host, 0x20), 'mode': get(host, 0x14)}
    assert original['ccu'] == 0x80000000, original
    assert original['top'] & 0x22 == 0x22, original
    try:
        put(host, 0x10, 3 << 16)
        put(tcon, 0, 0)
        if not internal:
            put(ccu, 0xb70, 0x80000002)  # 1188 MHz /3 = 396 MHz
            put(top, 0xc, original['top'] & ~(1 << 5))
        put(host, 0x14, 0)  # HSC by itself uses command-mode sequencing
        time.sleep(0.002)
        put(host, 0x20, 0x1f)
        put(host, 0x48, 0xf02)
        put(host, 0x10, (3 << 16) | 1)
        deadline = time.monotonic() + 0.04
        while get(host, 0x10) & 1 and time.monotonic() < deadline:
            time.sleep(0.0001)
        completed = not (get(host, 0x10) & 1)
        output = {'clock': 'internal' if internal else 'ccu-396MHz', 'hsc_completed': completed,
                  'hsc_phy': f'{get(phy, 0xe0):08x}', 'hsc_inst': f'{get(host, 0x2f0):08x}'}
        if completed:
            put(host, 0x20, 0xf)
            put(host, 0x14, original['mode'])
            put(tcon, 0, original['tcon'])
            time.sleep(0.001)
            put(host, 0x10, 3 << 16)
            put(host, 0x48, 0x63f07006)
            put(host, 0x10, (3 << 16) | 1)
            time.sleep(0.1)
            distinct = set()
            for _ in range(500):
                distinct.add(get(host, 0x2e0) & 8191)
                time.sleep(0.001)
            output.update({'video_phy': f'{get(phy, 0xe0):08x}',
                           'inst': f'{get(host, 0x2f0):08x}',
                           'fifo': f'{get(host, 0x2f4):08x}',
                           'distinct_lines': len(distinct),
                           'line_range': [min(distinct), max(distinct)]})
        print(json.dumps(output, indent=2), flush=True)
    finally:
        put(host, 0x10, 3 << 16)
        put(tcon, 0, 0)
        put(top, 0xc, original['top'])
        put(ccu, 0xb70, original['ccu'])
        put(host, 0x20, original['lp11'])
        put(host, 0x14, original['mode'])
        put(tcon, 0, original['tcon'])
        assert get(ccu, 0xb70) == original['ccu']
        assert get(top, 0xc) == original['top']
        print('CLOCK_MUX_AND_DIVIDER_RESTORED', flush=True)
        for memory in maps:
            memory.close()
        os.close(fd)
