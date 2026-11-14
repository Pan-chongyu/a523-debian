"""Same frozen ordinary memcpy workload, guarded by actual SPL voltage receipt."""
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import struct
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--seconds', type=int, default=300)
p.add_argument('--label', default='high-1')
p.add_argument('--low', action='store_true')
p.add_argument('--verify-only', action='store_true')
a = p.parse_args()
assert 30 <= a.seconds <= 600 and re.fullmatch('[a-z0-9-]{1,32}', a.label)
assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert Path('/sys/devices/system/cpu/online').read_text().strip() == '0-7'
assert int(Path('/proc/meminfo').read_text().splitlines()[0].split()[1]) > 3900000
assert not Path('/var/lib/tzx/gpu-qualified').exists()
for name in ('panfrost', 'tzx_cpufreq_divider', 'tzx_sram_log', 'tzx_cpu_stream_probe'):
    assert not Path('/sys/module', name).exists(), name
manifest = json.loads(Path('/home/debian/installed-bundle.json').read_text())
assert manifest['sha256'] == '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
fd = os.open('/dev/mmcblk0', os.O_RDONLY)
try:
    assert hashlib.sha256(os.pread(fd, 40960, 256*512)).hexdigest() == '311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75'
finally:
    os.close(fd)
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
try:
    with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x2e000) as view:
        receipt = [struct.unpack_from('<I', view, i)[0] for i in range(0x80, 0x94, 4)]
        assert receipt[:2] == [0xa523dc03, 1260] and receipt[2] in range(0xbc, 0xca)
        assert receipt[3:] == [0xc9, 2]
finally:
    os.close(fd)
status = json.loads(subprocess.check_output(['python3', '/home/debian/read_axp_dram_status.py'], timeout=20))
assert status['dcdc3_setpoint_mV'] == 1260 and status['axp717']['0x85'] == '0xc9'
for name in ('tzx-display', 'tzx-touch', 'tzx-wifi', 'tzx-bluetooth', 'tzx-audio',
             'tzx-battery', 'tzx-thermal', 'tzx-tablet-keys', 'lightdm', 'tzx-rtc-log'):
    assert subprocess.check_output(['systemctl', 'is-active', name], text=True, timeout=10).strip() == 'active', name
binary = Path('/home/debian/library-copy-coherency-v8')
assert hashlib.sha256(binary.read_bytes()).hexdigest() == '342d0c7e9bb52e84bfda236629d08382ea350c2abb35e4c2e7a320204e5ee517'
if a.verify_only:
    print('DRAM_BOOT_1260_HARDWARE_GUARDS_PASS', flush=True)
    raise SystemExit(0)
prefix = '/home/debian/copy-dram-boot-1260-v8-'+a.label
assert not list(Path('/home/debian').glob(Path(prefix).name+'-*'))
print('DRAM_BOOT_1260_COPY_BEGIN', json.dumps({
    'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'seconds': a.seconds, 'voltage_hook_receipt': receipt,
    'copy': 'unchanged libc, no added DSB', 'high_targets': not a.low,
    'full_4GiB': True, 'cpu_mask': '0-7'}), flush=True)
os.sync()
Path('/proc/sys/vm/drop_caches').write_text('1\n')
env = dict(os.environ)
env.pop('TZX_COPY_HIGH_TARGETS', None)
if not a.low:
    env['TZX_COPY_HIGH_TARGETS'] = '1'
result = subprocess.run([str(binary), str(a.seconds), prefix, '255', 'libc'], env=env,
                        timeout=a.seconds+55)
print('DRAM_BOOT_1260_COPY_RESULT', result.returncode, flush=True)
raise SystemExit(result.returncode)
