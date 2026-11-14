"""Bounded CPU-copy isolation; restores Wi-Fi even when the probe fails."""
import hashlib
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert not Path('/sys/module/panfrost').exists()
assert not Path('/sys/module/tzx_cpufreq_divider').exists()
binary = Path('/home/debian/library-copy-coherency-v4')
print('CPU_COPY_WIFI_ISOLATION_BEGIN', hashlib.sha256(binary.read_bytes()).hexdigest(), flush=True)
active = subprocess.run(['systemctl', 'is-active', '--quiet', 'tzx-wifi.service']).returncode == 0
assert active
try:
    subprocess.run(['systemctl', 'stop', 'tzx-wifi.service'], check=True, timeout=40)
    modules = Path('/proc/modules').read_text()
    assert 'aic8800_fdrv ' not in modules and 'aic8800_bsp ' not in modules, modules
    print('CPU_COPY_WIFI_UNLOADED', flush=True)
    binary.chmod(0o755)
    result = subprocess.run([str(binary), '60', '/home/debian/copy-nowifi-8cpu', '255', 'libc'], timeout=85)
    print('CPU_COPY_WIFI_ISOLATION_RESULT', result.returncode, flush=True)
finally:
    subprocess.run(['systemctl', 'start', 'tzx-wifi.service'], check=True, timeout=60)
    print('CPU_COPY_WIFI_RESTORED', flush=True)
