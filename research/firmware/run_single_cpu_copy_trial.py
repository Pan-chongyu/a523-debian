"""Bounded high-address copy trial with only CPU0 online; no register writes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

sha = lambda data: hashlib.sha256(data).hexdigest()
assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/devices/system/cpu/online').read_text().strip() == '0'
assert 'maxcpus=1' in Path('/proc/cmdline').read_text().split()
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
for module in ('panfrost', 'tzx_cpufreq_divider', 'tzx_sram_log', 'tzx_cpu_stream_probe'):
    assert not Path('/sys/module', module).exists(), module
manifest = json.loads(Path('/home/debian/installed-bundle.json').read_text())
assert manifest['sha256'] == 'c07fa1ff67b73f637d7213599f1e9b727c5ec3a6b9bc7b5dca718bdbbf0c9cbd'
fd = os.open('/dev/mmcblk0', os.O_RDONLY)
try:
    bundle = os.pread(fd, manifest['bytes'], manifest['start_lba']*512)
    assert sha(bundle) == manifest['sha256']
    assert os.pread(fd, 512, 4096*512) == bundle[:512]
finally:
    os.close(fd)
binary = Path('/home/debian/library-copy-coherency-v7')
assert sha(binary.read_bytes()) == '86d65c7f7d431b459cad4cfa3224d32758a98c1849b78d4d3caea45652da9b9c'
binary.chmod(0o755)
prefix = '/home/debian/copy-single-cpu-v7-high'
assert not list(Path('/home/debian').glob('copy-single-cpu-v7-high-*.bin'))
print('SINGLE_CPU_COPY_TRIAL_BEGIN', json.dumps({
    'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'online_cpu_mask': '0', 'duration_seconds': 300,
    'copy': 'ordinary libc, no added DSB', 'high_targets': True,
    'gpu_loaded': False, 'cpufreq_loaded': False}), flush=True)
# Release clean file cache so the high-address zone can supply the test buffers.
# The test later releases the unused pool before copying; no storage files change.
os.sync()
Path('/proc/sys/vm/drop_caches').write_text('1\n')
env = dict(os.environ, TZX_COPY_HIGH_TARGETS='1')
result = subprocess.run([str(binary), '300', prefix, '1', 'libc'], env=env, timeout=355)
print('SINGLE_CPU_COPY_TRIAL_RESULT', result.returncode, flush=True)
raise SystemExit(result.returncode)
