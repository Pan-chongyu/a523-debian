"""Run the lower address-window GPU comparison after the CPU-only check passes."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/devices/system/cpu/online').read_text().strip() == '0-7'
assert struct.unpack('>4I',Path('/sys/firmware/devicetree/base/memory@40000000/reg').read_bytes()) == (0,0x40000000,0,0xc0000000)
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
for name in ('panfrost','tzx_cpufreq_divider','tzx_cpu_stream_probe','tzx_sram_log'):
    assert not Path('/sys/module',name).exists(), name
assert not Path('/var/lib/tzx/gpu-qualified').exists()
manifest = json.loads(Path('/home/debian/low-window-gpu-MANIFEST.json').read_text())
assert manifest['diagnostic_only'] and manifest['memory_pressure_mib'] == 1792
for name,digest in manifest['files'].items():
    assert '/' not in name and hashlib.sha256(Path('/home/debian',name).read_bytes()).hexdigest() == digest, name
for unit,marker in (('tzx-k5-low-window-copy.service','LIBRARY_FIXED_COPY_PASS'),
                    ('tzx-k5-low-window-before-gpu-files.service','MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS')):
    state = subprocess.check_output(['systemctl','show',unit,'-p','Result','-p','ExecMainStatus','-p','ActiveState'],text=True)
    assert 'Result=success' in state and 'ExecMainStatus=0' in state and 'ActiveState=inactive' in state, state
    log = subprocess.check_output(['journalctl','-b','-u',unit,'-o','cat','--no-pager'],text=True)
    assert marker in log and 'MISMATCH' not in log
print('LOW_WINDOW_GPU_COMPARISON_BEGIN',Path('/proc/sys/kernel/random/boot_id').read_text().strip(),flush=True)
subprocess.run(['python3','/usr/local/lib/tzx-rtc-context/runtime.py','--live'],check=True,timeout=15)
subprocess.run(['python3','/home/debian/run_guarded_gpu_low_window.py','--label','k5-low-window-3g-1792',
    '--aarch64-pgtable','--keep-awake'],check=True,timeout=770)
