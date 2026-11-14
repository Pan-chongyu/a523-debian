"""CPU-only copy test on #5 with all memory advertised below physical 4GiB."""
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
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert struct.unpack('>4I',Path('/sys/firmware/devicetree/base/memory@40000000/reg').read_bytes()) == (0,0x40000000,0,0xc0000000)
for name in ('panfrost','tzx_cpufreq_divider','tzx_cpu_stream_probe','tzx_sram_log'):
    assert not Path('/sys/module',name).exists(), name
manifest = json.loads(Path('/home/debian/installed-bundle.json').read_text())
assert manifest['sha256'] == '0d9c3e238b5910f299c24d9c09d2a759e06076756150f5560a0f8af3148da985'
binary = Path('/home/debian/library-copy-coherency-v8')
assert hashlib.sha256(binary.read_bytes()).hexdigest() == '342d0c7e9bb52e84bfda236629d08382ea350c2abb35e4c2e7a320204e5ee517'
prefix = '/home/debian/copy-low-window-k5-v8'
assert not list(Path('/home/debian').glob('copy-low-window-k5-v8-*'))
binary.chmod(0o755)
os.sync()
Path('/proc/sys/vm/drop_caches').write_text('1\n')
env = {k:v for k,v in os.environ.items() if k not in ('TZX_COPY_HIGH_TARGETS','TZX_COPY_LOW_TARGETS')}
print('LOW_WINDOW_CPU_COPY_BEGIN',json.dumps({'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'seconds':300,'ordinary_libc_no_added_DSB':True,'original_BL31':True}),flush=True)
result = subprocess.run([str(binary),'300',prefix,'255','libc'],env=env,timeout=340)
print('LOW_WINDOW_CPU_COPY_RESULT',result.returncode,flush=True)
raise SystemExit(result.returncode)
