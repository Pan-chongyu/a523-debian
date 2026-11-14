"""Repeat the failed scene under the independently checked retained logger."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid()==0 and os.uname().release=='7.3.3-tzx-a523-accel1'
assert '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
assert json.loads(Path('/home/debian/installed-bundle.json').read_text())['sha256']=='4a6681c64fc6b173eedf6d3e28062be9596d6ea0c6c1a54b391cdb18a3fce9a9'
assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
for name in ('panfrost','tzx_cpufreq_divider','tzx_sram_log','tzx_cpu_stream_probe'):
    assert not Path('/sys/module',name).exists(),name
assert Path('/sys/module/tzx_rtc_log').exists()
assert hashlib.sha256(Path('/usr/local/lib/tzx-rtc-context/tzx_rtc_log.ko').read_bytes()).hexdigest()=='bb446382bdfec6fb87120540f67bd521851149538547f3c162697a2bb9eb22bb'
unit='tzx-bl31-prefetch-after-reset-files.service'
state=subprocess.check_output(['systemctl','show',unit,'-p','ActiveState','-p','Result','-p','ExecMainStatus'],text=True)
assert 'Result=success' in state and 'ActiveState=inactive' in state and 'ExecMainStatus=0' in state,state
log=subprocess.check_output(['journalctl','-b','-u',unit,'-o','cat','--no-pager'],text=True)
assert 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS' in log
subprocess.run(['python3','/home/debian/check_bl31_prefetch_registers.py'],check=True,timeout=30)
subprocess.run(['python3','/usr/local/lib/tzx-rtc-context/runtime.py','--live'],check=True,timeout=20)
print('PREFETCH_GPU_ABORT_CONTEXT_PROBE_BEGIN',Path('/proc/sys/kernel/random/boot_id').read_text().strip(),flush=True)
subprocess.run(['python3','/home/debian/run_guarded_gpu_trial.py','--label','bl31-prefetch-context',
    '--aarch64-pgtable','--keep-awake'],check=True,timeout=770)
print('PREFETCH_GPU_ABORT_CONTEXT_PROBE_SUITE_PASS',flush=True)
