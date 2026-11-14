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
assert manifest['sha256'] == '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
binary = Path('/home/debian/library-copy-coherency-v8')
assert hashlib.sha256(binary.read_bytes()).hexdigest() == '342d0c7e9bb52e84bfda236629d08382ea350c2abb35e4c2e7a320204e5ee517'
binary.chmod(0o755)
prefix = '/home/debian/copy-readonly-v8-high'
assert not list(Path('/home/debian').glob('copy-readonly-v8-high-*'))
print('GUARDED_COPY_TRIAL_BEGIN', json.dumps({
    'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'online_cpu_mask': '0-7', 'duration_seconds': 300,
    'copy': 'ordinary libc, no added DSB', 'reference_mprotect_readonly': True,
    'high_targets': True, 'gpu_loaded': False, 'cpufreq_loaded': False}), flush=True)
os.sync()
Path('/proc/sys/vm/drop_caches').write_text('1\n')
result = subprocess.run([str(binary), '300', prefix, '255', 'libc'],
                        env=dict(os.environ, TZX_COPY_HIGH_TARGETS='1'), timeout=355)
print('GUARDED_COPY_TRIAL_RESULT', result.returncode, flush=True)
raise SystemExit(result.returncode)
