"""Verify low physical targets as well, without changing the copy loop."""
import hashlib
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0
subprocess.run(['python3', '/home/debian/run_dram_boot_copy_trial.py', '--verify-only'], check=True, timeout=40)
binary = Path('/home/debian/library-copy-low-v9')
assert hashlib.sha256(binary.read_bytes()).hexdigest() == '4b6542e6ef80beb4aa78f69017d92f368f30753237045a208e4310a98809809f'
prefix = '/home/debian/copy-dram-boot-1260-v9-low-1'
assert not list(Path('/home/debian').glob(Path(prefix).name+'-*'))
os.sync()
Path('/proc/sys/vm/drop_caches').write_text('1\n')
env = dict(os.environ, TZX_COPY_LOW_TARGETS='1')
env.pop('TZX_COPY_HIGH_TARGETS', None)
print('DRAM_BOOT_1260_LOW_TARGET_COPY_BEGIN', Path('/proc/sys/kernel/random/boot_id').read_text().strip(), flush=True)
result = subprocess.run([str(binary), '120', prefix, '255', 'libc'], env=env, timeout=175)
print('DRAM_BOOT_1260_LOW_TARGET_COPY_RESULT', result.returncode, flush=True)
raise SystemExit(result.returncode)
