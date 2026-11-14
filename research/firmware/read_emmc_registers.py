import json,mmap,os,struct
from pathlib import Path
control=Path('/sys/class/mmc_host/mmc0/device/power/control')
original=control.read_text().strip();control.write_text('on')
fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
try:
    with mmap.mmap(fd,0x1000,access=mmap.ACCESS_READ,offset=0x04022000) as mem:
        print(json.dumps({hex(offset):hex(struct.unpack_from('<I',mem,offset)[0]) for offset in (0,4,0x54,0x5c,0x10c,0x140,0x144,0x148,0x14c,0x184,0x300)},indent=2))
finally:
    os.close(fd)
    control.write_text(original)
