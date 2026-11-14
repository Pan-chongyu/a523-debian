"""One explicit GPU comparison after both CPU copy placement checks pass."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert json.loads(Path('/home/debian/installed-bundle.json').read_text())['sha256'] == '4a6681c64fc6b173eedf6d3e28062be9596d6ea0c6c1a54b391cdb18a3fce9a9'
for name in ('panfrost', 'tzx_cpufreq_divider', 'tzx_sram_log', 'tzx_cpu_stream_probe'):
    assert not Path('/sys/module',name).exists(), name
for unit in ('tzx-bl31-prefetch-copy.service', 'tzx-bl31-prefetch-natural-copy.service', 'tzx-bl31-prefetch-low-copy.service'):
    state = subprocess.check_output(['systemctl','show',unit,'-p','ActiveState','-p','Result',
                                     '-p','ExecMainStatus'], text=True)
    assert 'ActiveState=inactive' in state and 'Result=success' in state and 'ExecMainStatus=0' in state, state
    log = subprocess.check_output(['journalctl','-b','-u',unit,'--no-pager','-o','cat'], text=True)
    assert 'LIBRARY_FIXED_COPY_PASS' in log and 'MISMATCH' not in log, unit
unit = 'tzx-bl31-prefetch-files-before-gpu.service'
state = subprocess.check_output(['systemctl','show',unit,'-p','ActiveState','-p','Result','-p','ExecMainStatus'],text=True)
assert 'ActiveState=inactive' in state and 'Result=success' in state and 'ExecMainStatus=0' in state, state
log = subprocess.check_output(['journalctl','-b','-u',unit,'-o','cat','--no-pager'],text=True)
assert 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS' in log and 'Traceback' not in log
subprocess.run(['python3','/home/debian/check_bl31_prefetch_registers.py'],check=True,timeout=30)
print('BL31_PREFETCH_GPU_TRIAL_BEGIN',Path('/proc/sys/kernel/random/boot_id').read_text().strip(),flush=True)
subprocess.run(['python3','/home/debian/run_guarded_gpu_trial.py',
    '--label','bl31-prefetch-first','--aarch64-pgtable','--keep-awake'],check=True,timeout=770)
print('BL31_PREFETCH_GPU_SUITE_COMPLETED',flush=True)
