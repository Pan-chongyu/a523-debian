"""Full-RAM GPU comparison only after CPU copies and package audit pass."""
import argparse
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--label', default='dram-boot-1260-first')
p.add_argument('--allow-autosuspend', action='store_true')
p.add_argument('--after-reboot', action='store_true')
a = p.parse_args()
assert a.label.startswith('dram-boot-1260-') and all(c.isalnum() or c == '-' for c in a.label)
assert os.geteuid() == 0
subprocess.run(['python3', '/home/debian/run_dram_boot_copy_trial.py', '--verify-only'],
               check=True, timeout=40)
checks = [('tzx-dram-boot-copy-after-reboot.service', 'LIBRARY_FIXED_COPY_PASS'),
          ('tzx-dram-boot-reboot-files-before-gpu.service', 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS')] if a.after_reboot else [
    ('tzx-dram-boot-copy-high-1.service', 'LIBRARY_FIXED_COPY_PASS'),
    ('tzx-dram-boot-copy-natural-1.service', 'LIBRARY_FIXED_COPY_PASS'),
    ('tzx-dram-boot-files-before-gpu.service', 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS')]
for name, marker in checks:
    state = subprocess.check_output(['systemctl', 'show', name, '-p', 'ActiveState',
                                     '-p', 'Result', '-p', 'ExecMainStatus'], text=True)
    assert 'ActiveState=inactive' in state and 'Result=success' in state and 'ExecMainStatus=0' in state, state
    log = subprocess.check_output(['journalctl', '-b', '-u', name, '-o', 'cat', '--no-pager'], text=True)
    assert marker in log and 'MISMATCH' not in log and 'Traceback' not in log, name
print('DRAM_BOOT_1260_GPU_COMPARISON_BEGIN', Path('/proc/sys/kernel/random/boot_id').read_text().strip(), flush=True)
subprocess.run(['python3', '/usr/local/lib/tzx-rtc-context/runtime.py', '--live'], check=True, timeout=20)
command = ['python3', '/home/debian/run_guarded_gpu_trial.py', '--label', a.label, '--aarch64-pgtable']
if not a.allow_autosuspend:
    command.append('--keep-awake')
env = dict(os.environ)
env['TZX_GPU_EXPECT_AWAKE'] = '0' if a.allow_autosuspend else '1'
subprocess.run(command, check=True, timeout=770, env=env)
print('DRAM_BOOT_1260_FULL_RAM_GPU_SUITE_COMPLETED', flush=True)
