"""Restore the software desktop, then return both CPU clusters to schedutil."""
import subprocess

try:
    subprocess.run(['/usr/bin/python3', '/home/debian/cleanup_gpu_dma32_trial.py',
                    '--restart-desktop'], check=True, timeout=90)
finally:
    subprocess.run(['/usr/bin/systemctl', 'start', 'tzx-cpufreq.service'],
                   check=True, timeout=45)
    subprocess.run(['/usr/bin/systemctl', 'is-active', 'tzx-cpufreq.service'],
                   check=True, timeout=15)
print('GPU_K5_TRIAL_CLEANED_DESKTOP_AND_CPUFREQ_RESTORED', flush=True)
