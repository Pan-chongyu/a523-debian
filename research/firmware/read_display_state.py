"""Read the exact board's display-related CCU and GPIO state, without writes."""
import json
import mmap
import os
from pathlib import Path
import struct

assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
registers = {
    'DSI1_CLK': 0x02001b28, 'DSI_BUS_RESET': 0x02001b4c,
    'COMBOPHY_DSI1_CLK': 0x02001b70,
    'TCON1_CLK': 0x02001b64, 'TCON_BUS_RESET': 0x02001b7c,
    'DISPLAY_TOP_RESET': 0x02001abc, 'PWM_BUS_RESET': 0x020017ac,
    'PD_CFG0': 0x02000090, 'PD_CFG1': 0x02000094,
    'PD_CFG2': 0x02000098, 'PD_DATA': 0x020000a0,
    'PH_CFG0': 0x02000150, 'PH_CFG1': 0x02000154,
    'PH_CFG2': 0x02000158, 'PH_DATA': 0x02000160,
    'PWM0_GATE': 0x02000c40,
    'PIO_POW_MOD_SEL': 0x02000380,
    'PIO_POW_MOD_CTRL': 0x02000384,
    'PIO_POW_VAL': 0x02000388,
    'PIO_POW_CTRL': 0x02000390,
}
result = {}
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
try:
    for name, address in registers.items():
        with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ,
                       offset=address & ~4095) as memory:
            result[name] = f'0x{struct.unpack_from("<I", memory, address & 4095)[0]:08x}'
finally:
    os.close(fd)
print(json.dumps(result, indent=2))
