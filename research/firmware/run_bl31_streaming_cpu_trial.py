"""Bounded CPU-only comparison for the independently staged EL3 candidate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--high-targets', action='store_true')
args = parser.parse_args()
sha = lambda data: hashlib.sha256(data).hexdigest()
assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert os.uname().release == '7.3.3-tzx-a523-accel1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert Path('/sys/devices/system/cpu/online').read_text().strip() == '0-7'
for module in ('panfrost', 'tzx_cpufreq_divider', 'tzx_sram_log', 'tzx_cpu_stream_probe'):
    assert not Path('/sys/module', module).exists(), module
manifest = json.loads(Path('/home/debian/installed-bundle.json').read_text())
assert manifest['sha256'] == '165f940df7bcd97bddce20ec927d53fe32bcf3581fadbd3c10c5404484671e8a'
bl31 = next(item for item in manifest['items'] if item['file'] == 'bl31.bin')
fd = os.open('/dev/mmcblk0', os.O_RDONLY)
try:
    assert sha(os.pread(fd, bl31['bytes'], bl31['lba']*512)) == '573865c541b221a8c55dada09496de61ecc3d93eb7641b6713e0412db5e36579'
finally:
    os.close(fd)
binary = Path('/home/debian/library-copy-coherency-v7')
assert sha(binary.read_bytes()) == '86d65c7f7d431b459cad4cfa3224d32758a98c1849b78d4d3caea45652da9b9c'
binary.chmod(0o755)
mode = 'high' if args.high_targets else 'natural'
print('BL31_STREAM_CPU_TRIAL_BEGIN', json.dumps({
    'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'targets': mode, 'duration_seconds': 300, 'copy': 'ordinary libc, no added DSB',
    'gpu_loaded': False, 'cpufreq_loaded': False}), flush=True)
env = dict(os.environ)
env.pop('TZX_COPY_HIGH_TARGETS', None)
if args.high_targets:
    env['TZX_COPY_HIGH_TARGETS'] = '1'
result = subprocess.run([str(binary), '300', '/home/debian/bl31-stream-v7-'+mode,
                         '255', 'libc'], env=env, timeout=355)
print('BL31_STREAM_CPU_TRIAL_RESULT', mode, result.returncode, flush=True)
raise SystemExit(result.returncode)
