"""Durable manual-only unit installation, with the startup rail untouched."""
import hashlib
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0
subprocess.run(['python3', '/home/debian/run_dram_boot_copy_trial.py', '--verify-only'], check=True, timeout=40)
base = Path('/home/debian')
for name in ('run_dram_boot_gpu_trial.py', 'finish_dram_boot_gpu_trial.py',
             'run_dram_boot_copy_trial.py'):
    path = base/name
    data = path.read_bytes()
    compile(data, str(path), 'exec')
    fd = os.open(path, os.O_RDONLY)
    os.fsync(fd)
    os.close(fd)
    print('DRAM_BOOT_GPU_SCRIPT_DURABLE', name, hashlib.sha256(data).hexdigest(), flush=True)
source = base/'tzx-dram-boot-gpu-diagnostic.service'
data = source.read_bytes()
assert b'[Install]' not in data and b'RuntimeMaxSec=800s' in data
assert b'ExecStopPost=/usr/bin/python3 -u /home/debian/finish_dram_boot_gpu_trial.py' in data
target = Path('/etc/systemd/system/tzx-dram-boot-gpu-diagnostic.service')
assert not target.exists() and not target.is_symlink()
temporary = target.with_suffix('.service.new')
with temporary.open('wb') as f:
    f.write(data)
    f.flush()
    os.fchmod(f.fileno(), 0o644)
    os.fsync(f.fileno())
temporary.replace(target)
fd = os.open(target.parent, os.O_DIRECTORY)
os.fsync(fd)
os.close(fd)
subprocess.run(['systemd-analyze', 'verify', str(target)], check=True, timeout=30)
subprocess.run(['systemctl', 'daemon-reload'], check=True, timeout=30)
assert subprocess.check_output(['systemctl', 'is-enabled', target.name], text=True).strip() == 'static'
os.sync()
print('DRAM_BOOT_GPU_MANUAL_ONLY_UNIT_READY', flush=True)
