"""One explicit GPU comparison after both CPU copy placement checks pass."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert json.loads(Path('/home/debian/installed-bundle.json').read_text())['sha256'] == '165f940df7bcd97bddce20ec927d53fe32bcf3581fadbd3c10c5404484671e8a'
for name in ('panfrost', 'tzx_cpufreq_divider', 'tzx_sram_log', 'tzx_cpu_stream_probe'):
    assert not Path('/sys/module',name).exists(), name
for unit in ('tzx-bl31-stream-copy-300', 'tzx-bl31-stream-high-v7-aftercache'):
    state = subprocess.check_output(['systemctl','show',unit,'-p','ActiveState','-p','Result',
                                     '-p','ExecMainStatus'], text=True)
    assert 'ActiveState=inactive' in state and 'Result=success' in state and 'ExecMainStatus=0' in state, state
    log = subprocess.check_output(['journalctl','-b','-u',unit,'--no-pager','-o','cat'], text=True)
    assert 'LIBRARY_FIXED_COPY_PASS' in log and 'MISMATCH' not in log, unit
probe = Path('/home/debian/tzx_cpu_stream_readonly.ko')
assert hashlib.sha256(probe.read_bytes()).hexdigest() == 'daed55465d9d3bcbfda55f167565fc097d95cc0e5326b8c08b9072428d235533'
subprocess.run(['insmod',str(probe)],check=True,timeout=15)
try:
    rows = subprocess.check_output(['dmesg'],text=True).splitlines()[-8:]
    assert len(rows) == 8 and all('cpuectlr=000000007e08bc00' in row for row in rows), rows
    assert {int(row.split(' cpu',1)[1].split()[0]) for row in rows} == set(range(8)), rows
    for row in rows:
        print('BL31_STREAM_GPU_CPU_REGISTER',row,flush=True)
finally:
    subprocess.run(['rmmod','tzx_cpu_stream_probe'],check=True,timeout=15)
print('BL31_STREAM_GPU_TRIAL_BEGIN',Path('/proc/sys/kernel/random/boot_id').read_text().strip(),flush=True)
subprocess.run(['python3','/home/debian/run_guarded_gpu_trial.py',
    '--label','bl31-stream-first','--aarch64-pgtable','--keep-awake'],check=True,timeout=770)
print('BL31_STREAM_GPU_SUITE_COMPLETED',flush=True)
