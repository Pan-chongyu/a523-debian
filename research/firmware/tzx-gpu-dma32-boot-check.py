"""Validate the installed GPU desktop after boot; never change voltage/clocks."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from tzx_direct_io import read_direct

assert os.geteuid() == 0 and '#4 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/var/lib/tzx/gpu-qualified').exists()
assert Path('/sys/module/panfrost/parameters/tzx_dma32').read_text().strip() == 'Y'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                if line.startswith('MemTotal:'))) > 3900000
subprocess.run(['systemctl', 'is-active', '--quiet', 'tzx-gpu.service'], check=True)
subprocess.run(['sha256sum', '-c', '/usr/local/lib/tzx-gpu-dma32/MODULES.sha256'], check=True)
environment = dict(os.environ, DISPLAY=':0', XAUTHORITY='/run/lightdm/root/:0')
for attempt in range(25):
    result = subprocess.run(['glxinfo', '-B'], env=environment, capture_output=True,
                            text=True, timeout=5)
    if result.returncode == 0 and 'Mali-G57' in result.stdout and 'Accelerated: yes' in result.stdout:
        break
    time.sleep(1)
else:
    raise RuntimeError('GPU desktop unavailable after boot')
subprocess.run(['python3', '/usr/local/lib/tzx-accel-hardware/verify_gpu_render.py',
                '--node', '/dev/dri/by-path/platform-tzx-de-scanout-card'], check=True, timeout=18)
sentinel = os.urandom(32 * 1024 * 1024)
digest = hashlib.sha256(sentinel).digest()
files = [Path('/usr/bin/glmark2-es2-drm'), Path('/usr/lib/aarch64-linux-gnu/libc.so.6'),
         Path('/usr/lib/aarch64-linux-gnu/libpcre2-8.so.0.14.0')]
files.extend(Path('/usr/lib/aarch64-linux-gnu').glob('libgallium-*.so'))
for path in files:
    read_direct(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
assert hashlib.sha256(sentinel).digest() == digest
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
faults = [line for line in subprocess.check_output(['dmesg'], text=True).splitlines()
          if 'panfrost' in line and any(word in line for word in ('fault', 'timeout'))]
assert not faults, faults
temperatures = {zone.joinpath('type').read_text().strip(): int(zone.joinpath('temp').read_text())
                for zone in Path('/sys/class/thermal').glob('thermal_zone*')}
assert len(temperatures) == 5 and all(0 < value < 75000 for value in temperatures.values())
report = {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'gpu_desktop': 'Mali-G57 (Panfrost)', 'full_4GiB': True,
          'module_hashes_pixel_readback_and_critical_file_reads': 'PASS',
          'temperatures_mC': temperatures, 'kernel_taint': 4096}
Path('/var/lib/tzx/gpu-dma32-boot-health.json').write_text(json.dumps(report, indent=2) + '\n')
print('GPU_DMA32_BOOT_HEALTH_PASS', json.dumps(report), flush=True)
