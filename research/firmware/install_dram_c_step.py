"""Durably install only the manual diagnostic and its recovery helper."""
import hashlib
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert not Path('/sys/module/panfrost').exists()
assert not Path('/sys/module/tzx_cpufreq_divider').exists()
assert not list(Path('/home/debian').glob('copy-dram-c-step-1200-v8-*'))
files = {
    'axp717-dram-step': ('/usr/local/lib/tzx-dram-c-step/control', 0o700,
                       '9586ea51c859ec7b0f127d4a757f907ac31da9ca270d90dadc5185cf065556b3'),
}
for name in ('tzx-dram-c-step-1200.service', 'tzx-dram-c-step-boot-restore.service'):
    files[name] = ('/etc/systemd/system/'+name, 0o644, None)
assert hashlib.sha256(Path('/home/debian/library-copy-coherency-v8').read_bytes()).hexdigest() == '342d0c7e9bb52e84bfda236629d08382ea350c2abb35e4c2e7a320204e5ee517'
for name, (target, mode, digest) in files.items():
    data = Path('/home/debian', name).read_bytes()
    assert len(data) > 300
    if digest is not None:
        assert hashlib.sha256(data).hexdigest() == digest
    else:
        assert b'ExecStart=' in data and b'Description=' in data
        assert b'[Service]' in data and b'/usr/local/lib/tzx-dram-c-step/control' in data
    path = Path(target)
    assert not path.is_symlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.new')
    with temporary.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fchmod(stream.fileno(), mode)
        os.fchown(stream.fileno(), 0, 0)
        os.fsync(stream.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    assert path.read_bytes() == data
    print('DRAM_C_INSTALLED_DURABLE', target, len(data), hashlib.sha256(data).hexdigest(), flush=True)
directory = Path('/var/lib/tzx/diagnostics/dram-c-step')
directory.mkdir(mode=0o700, parents=True, exist_ok=True)
assert directory.stat().st_uid == 0
old = Path('/etc/systemd/system/multi-user.target.wants/tzx-dram-step-boot-restore.service')
if old.is_symlink():
    assert os.readlink(old) == '/etc/systemd/system/tzx-dram-step-boot-restore.service'
    old.unlink()
    fd = os.open(old.parent, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)
os.sync()
subprocess.run(['systemd-analyze', 'verify', *[target for target, _, _ in files.values() if target.endswith('.service')]], check=True, timeout=30)
subprocess.run(['systemctl', 'daemon-reload'], check=True, timeout=30)
subprocess.run(['systemctl', 'enable', 'tzx-dram-c-step-boot-restore.service'], check=True, timeout=30)
os.sync()
subprocess.run(['/usr/local/lib/tzx-dram-c-step/control', 'probe'], check=True, timeout=20)
print('DRAM_C_READY_NO_VOLTAGE_WRITE', flush=True)
