"""Restore verified libmount bytes and park GPU acceleration for diagnosis."""
import hashlib
import json
import mmap
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0 and os.uname().release == '7.3.3-tzx-a523-accel1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
path = Path('/usr/lib/aarch64-linux-gnu/libmount.so.1.1.0')
expected = '3b06ae574b3418292f1d90f366d2ab2d'
size = path.stat().st_size
fd = os.open(path, os.O_RDONLY | os.O_DIRECT)
buffer = mmap.mmap(-1, (size+4095)//4096*4096)
read = os.readv(fd, [buffer])
os.close(fd)
data = buffer[:read]
buffer.close()
assert read == size and hashlib.md5(data).hexdigest() == expected
temporary = path.with_name(path.name+'.tzx-good')
with temporary.open('wb') as stream:
    stream.write(data)
    stream.flush()
    os.fsync(stream.fileno())
temporary.chmod(0o644)
temporary.replace(path)
assert hashlib.md5(path.read_bytes()).hexdigest() == expected
print('LIBMOUNT_RESTORED_FROM_VERIFIED_DIRECT_DISK_READ', flush=True)

overrides = Path('/usr/local/lib/tzx-accel/overrides.json')
old = overrides.read_bytes()
record = Path('/root/tzx-recovery/accel1')
record.mkdir(parents=True, exist_ok=True)
backup = record/'overrides-before-gpu-fallback.json'
if not backup.exists():
    backup.write_bytes(old)
values = json.loads(old)
values['lightdm.service'] = '''[Unit]
After=tzx-display.service tzx-thermal.service
[Service]
ExecStart=
ExecStart=/usr/sbin/lightdm
'''
overrides.write_text(json.dumps(values, indent=2)+'\n')
dropin = Path('/etc/systemd/system/tzx-gpu.service.d/90-unqualified.conf')
dropin.parent.mkdir(parents=True, exist_ok=True)
dropin.write_text('[Unit]\nConditionPathExists=/var/lib/tzx/gpu-qualified\n')
assert not Path('/var/lib/tzx/gpu-qualified').exists()
os.sync()
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemctl', 'stop', 'lightdm.service'], check=True)
subprocess.run(['systemctl', 'stop', 'tzx-gpu.service'], check=True)
subprocess.run(['modprobe', '-r', 'panfrost'], check=True)
subprocess.run(['systemctl', 'reset-failed', 'tzx-gpu-extended2.service'], check=True)
subprocess.run(['systemctl', 'start', 'lightdm.service'], check=True)
os.sync()
print('SOFTWARE_DESKTOP_RESTORED_GPU_PARKED', flush=True)
