"""Bounded low-address comparison of the same v8 copying loop."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0 and os.uname().release == '7.3.3-tzx-a523-accel1'
assert '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/devices/system/cpu/online').read_text().strip() == '0-7'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert json.loads(Path('/home/debian/installed-bundle.json').read_text())['sha256'] == '4a6681c64fc6b173eedf6d3e28062be9596d6ea0c6c1a54b391cdb18a3fce9a9'
for module in ('panfrost','tzx_cpufreq_divider','tzx_sram_log','tzx_cpu_stream_probe'):
    assert not Path('/sys/module',module).exists(), module
for unit in ('tzx-bl31-prefetch-copy.service','tzx-bl31-prefetch-natural-copy.service'):
    state = subprocess.check_output(['systemctl','show',unit,'-p','ActiveState','-p','Result','-p','ExecMainStatus'],text=True)
    assert 'ActiveState=inactive' in state and 'Result=success' in state and 'ExecMainStatus=0' in state, state
    log = subprocess.check_output(['journalctl','-b','-u',unit,'-o','cat','--no-pager'],text=True)
    assert 'LIBRARY_FIXED_COPY_PASS' in log and 'MISMATCH' not in log
binary = Path('/home/debian/library-copy-low-v9')
assert hashlib.sha256(binary.read_bytes()).hexdigest() == '4b6542e6ef80beb4aa78f69017d92f368f30753237045a208e4310a98809809f'
binary.chmod(0o755)
prefix = '/home/debian/copy-bl31-prefetch-v9-low'
assert not list(Path('/home/debian').glob('copy-bl31-prefetch-v9-low-*'))
print('PREFETCH_LOW_COPY_BEGIN',Path('/proc/sys/kernel/random/boot_id').read_text().strip(),flush=True)
os.sync()
Path('/proc/sys/vm/drop_caches').write_text('1\n')
result = subprocess.run([str(binary),'120',prefix,'255','libc'],
    env=dict(os.environ,TZX_COPY_LOW_TARGETS='1'),timeout=175)
print('PREFETCH_LOW_COPY_RESULT',result.returncode,flush=True)
raise SystemExit(result.returncode)
