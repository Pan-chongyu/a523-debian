"""Revoke GPU boot enablement and restore the software desktop on failure."""
import json
import os
from pathlib import Path
import subprocess
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
marker = Path('/var/lib/tzx/gpu-qualified')
if marker.exists():
    record = marker.read_text()
    marker.unlink()
    Path('/var/lib/tzx/gpu-dma32-disabled.json').write_text(json.dumps({
        'time_unix': int(time.time()), 'reason': 'GPU startup or boot-health failure',
        'previous_qualification': record}, indent=2) + '\n')
subprocess.run(['systemctl', 'restart', 'lightdm.service'], check=True, timeout=45)
subprocess.run(['systemctl', 'stop', 'tzx-gpu.service'], check=False, timeout=15)
if Path('/sys/module/panfrost').exists():
    subprocess.run(['modprobe', '-r', 'panfrost'], check=False, timeout=20)
os.sync()
print('GPU_DMA32_QUALIFICATION_REVOKED_SOFTWARE_DESKTOP_RESTARTED', flush=True)
