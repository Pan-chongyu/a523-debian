"""Manual bounded cache-write allocation comparison, with independent cleanup."""
raise SystemExit('RETIRED: EL1 CPUECTLR write faulted at MSR; use read-only sampling only')
import hashlib
import json
import os
from pathlib import Path
import subprocess

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/proc/version').read_text().split('#', 1)[1].startswith('5 ')
assert not Path('/sys/module/panfrost').exists()
assert not Path('/sys/module/tzx_cpufreq_divider').exists()
assert not Path('/sys/module/tzx_cpu_stream_probe').exists()
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
binary = '/home/debian/library-copy-coherency-v5'
assert digest(binary) == '5a7221a40a21ddbb6ed741e374102e6d9e7edf557ee96b4f6242e99b6c06663e'
module = '/home/debian/tzx_cpu_stream_probe.ko'
manifest = json.loads(Path('/home/debian/cpu-stream-probe-hash.json').read_text())
assert digest(module) == manifest['module_sha256']
print('CPU_STREAM_TRIAL_BEGIN', json.dumps({'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
      'module': manifest['module_sha256'], 'duration': 120, 'permanent_install': False}), flush=True)
try:
    subprocess.run(['insmod', module, 'disable_streaming=1'], check=True, timeout=15)
    print('CPU_STREAM_THRESHOLDS_DISABLED', flush=True)
    result = subprocess.run([binary, '120', '/home/debian/copy-streaming-disabled', '255', 'libc'], timeout=145)
    print('CPU_STREAM_COPY_RESULT', result.returncode, flush=True)
finally:
    if Path('/sys/module/tzx_cpu_stream_probe').exists():
        subprocess.run(['rmmod', 'tzx_cpu_stream_probe'], check=True, timeout=15)
    print('CPU_STREAM_ORIGINAL_THRESHOLDS_RESTORED', flush=True)
