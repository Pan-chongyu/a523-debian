"""Bounded v8 copy trial: immutable reference and complete PFN snapshots."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/devices/system/cpu/online').read_text().strip() == '0-7'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
for module in ('panfrost', 'tzx_cpufreq_divider', 'tzx_sram_log', 'tzx_cpu_stream_probe'):
    assert not Path('/sys/module', module).exists(), module
manifest = json.loads(Path('/home/debian/installed-bundle.json').read_text())
assert manifest['sha256'] == '4a6681c64fc6b173eedf6d3e28062be9596d6ea0c6c1a54b391cdb18a3fce9a9'
binary = Path('/home/debian/library-copy-coherency-v8')
assert hashlib.sha256(binary.read_bytes()).hexdigest() == '342d0c7e9bb52e84bfda236629d08382ea350c2abb35e4c2e7a320204e5ee517'
binary.chmod(0o755)
prefix = '/home/debian/copy-bl31-prefetch-v8-natural'
assert not list(Path('/home/debian').glob('copy-bl31-prefetch-v8-natural-*'))
state = subprocess.check_output(['systemctl','show','tzx-bl31-prefetch-copy.service',
    '-p','ActiveState','-p','Result','-p','ExecMainStatus'], text=True)
assert 'ActiveState=inactive' in state and 'Result=success' in state and 'ExecMainStatus=0' in state, state
log = subprocess.check_output(['journalctl','-b','-u','tzx-bl31-prefetch-copy.service','-o','cat','--no-pager'], text=True)
assert 'LIBRARY_FIXED_COPY_PASS' in log and 'MISMATCH' not in log
print('PREFETCH_COPY_TRIAL_BEGIN', json.dumps({
    'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'online_cpu_mask': '0-7', 'duration_seconds': 300,
    'copy': 'ordinary libc, no added DSB', 'reference_mprotect_readonly': True,
    'high_targets': False, 'gpu_loaded': False, 'cpufreq_loaded': False}), flush=True)
os.sync()
Path('/proc/sys/vm/drop_caches').write_text('1\n')
result = subprocess.run([str(binary), '300', prefix, '255', 'libc'],
                        env={k:v for k,v in os.environ.items() if k != 'TZX_COPY_HIGH_TARGETS'}, timeout=355)
print('PREFETCH_COPY_TRIAL_RESULT', result.returncode, flush=True)
raise SystemExit(result.returncode)
