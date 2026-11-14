"""Read the retained-display child's receipts without requiring a stopped DE."""
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct

assert os.geteuid() == 0
state = Path('/var/lib/tzx')
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
try:
    with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x4b000) as view:
        trained = list(struct.unpack_from('<32I', view, 0x85c))
    with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x2d000) as view:
        cpu = list(struct.unpack_from('<16I2Q', view, 0x500))
        profile = list(struct.unpack_from('<2I5Q8I', view, 0xc00))
        speed = list(struct.unpack_from('<4I4Q', view, 0x700))
        rail = struct.unpack_from('<Q', view, 0x740)[0]
finally:
    os.close(fd)
panel = json.loads((state/'boot-panel-stage.json').read_text())
logo = json.loads((state/'boot-logo-stage.json').read_text())
print(json.dumps(dict(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    trained_parameters=trained, trained_parameters_sha256=hashlib.sha256(struct.pack('<32I', *trained)).hexdigest(),
    cpu_receipt=cpu, profile_receipt=profile, speed_receipt=speed, rail_started_ticks=rail,
    panel=panel, logo=logo), indent=2))
