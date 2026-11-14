"""Restore only the files owned by this GPU package; reboot to reload modules."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
backup = Path('/root/tzx-recovery/gpu-dma32')
previous = json.loads((backup / 'before.json').read_text())
installed = json.loads((backup / 'installed-files.json').read_text())
assert set(previous) == set(installed)
Path('/var/lib/tzx/gpu-qualified').unlink(missing_ok=True)
subprocess.run(['systemctl', 'disable', 'tzx-gpu-dma32-health.service'], check=True)
for name, saved in previous.items():
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    target = Path('/') / name
    assert not target.is_symlink()
    if target.exists():
        assert hashlib.sha256(target.read_bytes()).hexdigest() == installed[name], name
    if saved is None:
        target.unlink(missing_ok=True)
    else:
        data = (backup / 'files' / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == saved['sha256']
        temporary = target.with_name(target.name + '.tzx-restore')
        temporary.write_bytes(data)
        temporary.chmod(saved['mode'])
        temporary.replace(target)
subprocess.run(['depmod', '-a', '7.3.3-tzx-a523-accel1'], check=True)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
os.sync()
print('GPU_DMA32_PACKAGE_BASELINE_FILES_RESTORED_REBOOT_REQUIRED', flush=True)
