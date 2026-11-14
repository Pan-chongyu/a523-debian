"""Read the boot loader's SRAM receipt/log with aligned 32-bit accesses."""
import json
import mmap
import os
from pathlib import Path
import struct

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
try:
    with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x2e000) as view:
        words = [struct.unpack_from('<I', view, offset)[0] for offset in range(0, 0x1000, 4)]
finally:
    os.close(fd)
raw = struct.pack('<1024I', *words)
record = {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'receipt': [hex(value) for value in words[:12]],
          'receipt_signature_valid': words[0] == 0x4452414d,
          'voltage_hook_receipt': [hex(value) for value in words[32:37]],
          'log': raw[0x100:0x100+3500].split(b'\0', 1)[0].decode('ascii', errors='replace')}
print(json.dumps(record, indent=2), flush=True)
