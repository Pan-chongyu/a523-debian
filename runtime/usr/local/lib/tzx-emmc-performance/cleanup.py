"""Independent 25MHz eMMC fallback, including supervisor SIGKILL."""
from pathlib import Path
import subprocess

assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == Path('/etc/tzx/device-cid').read_text().strip()
parameter = Path('/sys/module/tzx_emmc_performance/parameters/requested_mhz')
if parameter.exists():
    try:
        parameter.write_text('25')
    finally:
        subprocess.run(['rmmod','tzx_emmc_performance'],check=True,timeout=20)
assert Path('/sys/kernel/debug/mmc0/clock').read_text().strip() == '25000000'
Path('/var/lib/tzx/emmc-performance-pending.json').unlink(missing_ok=True)
print('EMMC_PERFORMANCE_ORIGINAL_25MHZ_RESTORED',flush=True)
