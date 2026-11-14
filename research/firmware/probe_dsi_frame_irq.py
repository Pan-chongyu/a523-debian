"""Observe a frame IRQ for four seconds, then restore the original IRQ mask."""
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/module/tzx_display/parameters/screen_revision').read_text().strip() == 'screen-functions-1'
module = Path('/home/debian/tzx_dsi_irq_probe.ko')
assert hashlib.sha256(module.read_bytes()).hexdigest() == '1c6d20c88dfe55af2aee0ed0e71ea2e6f04c79d9e6c10b8cae4cf9cee8e1aac0'
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def irq_mask():
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    try:
        with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x05508000) as view:
            return struct.unpack_from('<I', view, 4)[0] & 0xffff
    finally:
        os.close(fd)


before = irq_mask()
assert before == 0
data = {}
start = time.monotonic()
try:
    subprocess.run(['insmod', str(module)], check=True, timeout=10)
    time.sleep(4)
    folder = Path('/sys/module/tzx_dsi_irq_probe/parameters')
    data = {name: int((folder/name).read_text()) for name in ('frame_irqs', 'period_min_us', 'period_max_us', 'irq_storm')}
finally:
    if Path('/sys/module/tzx_dsi_irq_probe').exists():
        subprocess.run(['rmmod', 'tzx_dsi_irq_probe'], check=True, timeout=10)
elapsed = time.monotonic()-start
assert irq_mask() == before
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
data.update(boot_id=boot, elapsed_seconds=elapsed, original_IRQ_mask_restored=True)
data['result'] = 'PASS' if data['irq_storm'] == 0 and 220 <= data['frame_irqs'] <= 290 else 'NOT_QUALIFIED'
Path('/var/lib/tzx/dsi-frame-irq-probe.json').write_text(json.dumps(data, indent=2)+'\n')
print('TZX_DSI_FRAME_IRQ_PROBE', json.dumps(data), flush=True)
