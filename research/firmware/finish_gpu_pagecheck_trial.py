"""End the #6 diagnostic at the fixed CPU clocks used for its comparison."""
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0 and '#6 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
subprocess.run(['/usr/bin/python3', '/home/debian/cleanup_gpu_dma32_trial.py',
                '--restart-desktop'], check=True, timeout=90)
assert not Path('/sys/module/panfrost').exists()
assert not Path('/sys/module/tzx_cpufreq_divider').exists()
subprocess.run(['systemctl', 'is-active', 'lightdm', 'tzx-cpub.service'], check=True, timeout=15)
print('GPU_PAGECHECK_TRIAL_CLEANED_SOFTWARE_DESKTOP_FIXED_CPU_CLOCKS', flush=True)
