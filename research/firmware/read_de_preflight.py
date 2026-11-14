"""Read the A523 power/clock state without touching a powered-down DE bus."""
from pathlib import Path
import json
import mmap
import os
import struct

assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
result = {}
try:
    for name, address, length, offsets in (
        ('ccu', 0x02001000, 4096, (0x600, 0x60c, 0x804, 0x80c, 0xabc, 0xb4c, 0xb7c)),
        ('r_ccu', 0x07010000, 4096, (0x1ac,)),
        ('pck600', 0x07060000, 0x8000,
         tuple(base + off for base in (0x3000, 0x4000, 0x5000) for off in (0, 4, 8, 0x170, 0x174, 0xc00, 0xc04, 0xc10))),
    ):
        with mmap.mmap(fd, length, mmap.MAP_SHARED, mmap.PROT_READ, offset=address) as mem:
            result[name] = {f'{off:04x}': f'{struct.unpack_from("<I", mem, off)[0]:08x}' for off in offsets}
    if int(result['ccu']['060c'], 16) & 0x10001 == 0x10001:
        offsets = (0x8000, 0x8004, 0x8008, 0x8010, 0x8014, 0x8050, 0x8100, 0x8104, 0x8108, 0x810c, 0x8110, 0x8114, 0x8118, 0x811c, 0x1c1000, 0x1c1004, 0x281000, 0x28108c)
        with mmap.mmap(fd, 0x400000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x05000000) as mem:
            result['de'] = {f'{off:06x}': f'{struct.unpack_from("<I", mem, off)[0]:08x}' for off in offsets}
    else:
        result['de'] = 'not read: bus gated/reset asserted'
    print(json.dumps(result, indent=2))
finally:
    os.close(fd)
