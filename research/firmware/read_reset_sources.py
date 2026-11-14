"""Read documented watchdog state and the unused post-BL31 SRAM window."""
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert os.uname().release == '7.3.3-tzx-a523-accel1'
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
result = {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'time_unix': time.time(), 'access': 'read_only'}
try:
    for name, base, offset in [('cpux', 0x02050000, 0), ('cpus', 0x07020000, 0x400),
                               ('riscv', 0x07132000, 0)]:
        with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=base) as view:
            result[name] = {hex(off): hex(struct.unpack_from('<I', view, offset + off)[0])
                            for off in (0, 4, 0x10, 0x14, 0x18)}
    with mmap.mmap(fd, 8192, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x5e000) as view:
        data = view[:]
        result['unused_sram_5e000'] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                                       'nonzero_bytes': sum(bool(b) for b in data)}
        root = Path('/home/debian/tzx-reset-debug')
        root.mkdir(mode=0o700, exist_ok=True)
        snapshot = root / ('sram-before-' + result['boot_id'] + '.bin')
        with snapshot.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        result['sram_snapshot'] = str(snapshot)
finally:
    os.close(fd)
print(json.dumps(result, indent=2), flush=True)
