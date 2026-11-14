"""Restore the software display and audit files without runtime rail changes."""
from pathlib import Path
import subprocess

subprocess.run(['python3', '/home/debian/cleanup_gpu_dma32_trial.py', '--restart-desktop'], check=True, timeout=100)
assert not Path('/sys/module/panfrost').exists()
assert not Path('/sys/module/tzx_cpufreq_divider').exists()
subprocess.run(['python3', '/home/debian/read_axp_dram_status.py'], check=True, timeout=20)
subprocess.run(['python3', '/home/debian/verify_safe_memory.py', '--files-only'], check=True, timeout=140)
print('DRAM_BOOT_1260_GPU_CLEANUP_SOFTWARE_DESKTOP_AND_FILE_AUDIT_PASS', flush=True)
