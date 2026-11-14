"""Record the completed first-boot proof before the explicit warm-boot test."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0
subprocess.run(['python3', '/home/debian/run_dram_boot_copy_trial.py', '--verify-only'], check=True, timeout=40)
proof = {}
for unit, marker in [
    ('tzx-dram-boot-copy-high-1.service', 'copies=55193'),
    ('tzx-dram-boot-copy-natural-1.service', 'copies=55192'),
    ('tzx-dram-boot-copy-low-1.service', 'LIBRARY_FIXED_COPY_PASS'),
    ('tzx-dram-boot-gpu-diagnostic.service', 'DRAM_BOOT_1260_GPU_CLEANUP_SOFTWARE_DESKTOP_AND_FILE_AUDIT_PASS'),
]:
    state = subprocess.check_output(['systemctl', 'show', unit, '-p', 'ActiveState', '-p', 'Result', '-p', 'ExecMainStatus'], text=True)
    assert 'ActiveState=inactive' in state and 'Result=success' in state and 'ExecMainStatus=0' in state, state
    log = subprocess.check_output(['journalctl', '-b', '-u', unit, '-o', 'cat', '--no-pager'], text=True)
    assert marker in log and 'MISMATCH' not in log and 'Traceback' not in log, unit
    if 'gpu-diagnostic' in unit:
        assert 'GPU_FULL_X11_WITH_4_SCENES_AND_THREE_2560MIB_CPU_MEMORY_PASSES' in log
        assert 'GPU_CLOCKFIX_TWO_FULL_SCENE_PASSES' in log
        assert 'LIBRARY_PAGE_WATCH_CLEAN_STOP 1874' in log
    proof[unit] = {'journal_sha256': hashlib.sha256(log.encode()).hexdigest(), 'success_marker': marker}
record = {'state': 'first_boot_bounded_tests_passed_warm_boot_pending',
          'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'full_4GiB': True, 'copies_high_and_natural_600_seconds': 110385,
          'gpu_qualification_persisted': False, 'proof': proof}
target = Path('/var/lib/tzx/dram-boot-first-pass.json')
assert not target.exists()
temporary = target.with_suffix('.new')
with temporary.open('w') as f:
    json.dump(record, f, indent=2)
    f.write('\n')
    f.flush()
    os.fsync(f.fileno())
temporary.replace(target)
fd = os.open(target.parent, os.O_DIRECTORY)
os.fsync(fd)
os.close(fd)
os.sync()
print('DRAM_BOOT_FIRST_PASS_RECORDED_REBOOT_PENDING', json.dumps(record), flush=True)
subprocess.run(['systemd-run', '--unit=tzx-dram-boot-repeat-reboot', '--on-active=3s',
                '/usr/bin/systemctl', 'reboot'], check=True, timeout=20)
