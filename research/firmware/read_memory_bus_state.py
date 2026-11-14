"""Read aligned words of the exact A523 memory/interconnect configuration."""
import json
import mmap
import os
from pathlib import Path
import struct
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
groups = {
    'nsi_ra0_ta': (0x02023000,(0xc00,0xe00,0xea8)),
    'nsi_cpu': (0x02071000,(0x0,0x4,0x8,0x10,0x14,0x18)),
    'dram_common':(0x03120000,(0x0,0x4,0x8,0xc,0x10,0x14,0x20,0x24)),
    'dram_ctl':(0x03130000,(0x0,0x4,0x10,0x20,0x24,0x30,0x34,0x50,0x60,0x64,
                          0x200,0x204,0x208,0x20c,0x210,0x214,0x218,0x21c,0x220,0x224,0x228,0x22c,0x230)),
    'ccu_memory':(0x02001000,(0x10,0x540,0x800)),
    'cpu_pll':(0x08817000,(0x0,0x4,0x8,0xc,0x60,0x64,0x68)),
}
record = {'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'time_unix':time.time(),'access':'read_only_aligned_32bit'}
fd = os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
try:
    for name,(base,offsets) in groups.items():
        with mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ,offset=base) as view:
            record[name] = {hex(base+offset):hex(struct.unpack_from('<I',view,offset)[0])
                            for offset in offsets}
finally:
    os.close(fd)
print(json.dumps(record,indent=2),flush=True)
