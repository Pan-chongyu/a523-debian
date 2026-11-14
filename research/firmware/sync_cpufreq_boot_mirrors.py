"""Refresh file mirrors only after checking the active split-slot boot bundle."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct

assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
manifest_path = Path('/home/debian/cpufreq-framework-bundle.json')
manifest = json.loads(manifest_path.read_text())
assert manifest['start_lba'] == 65536 and manifest['header_lba'] == 4096
assert manifest['sha256'] == '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
with open('/dev/mmcblk0', 'rb', buffering=0) as disk:
    bundle = os.pread(disk.fileno(), manifest['bytes'], 65536 * 512)
    assert os.pread(disk.fileno(), 512, 4096 * 512) == bundle[:512]
    loader = os.pread(disk.fileno(), 40960, 256 * 512)
assert hashlib.sha256(loader).hexdigest() == 'ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df'
assert hashlib.sha256(bundle).hexdigest() == manifest['sha256']
copies = {}
for item in manifest['items'][:3]:
    offset = (item['lba'] - 65536) * 512
    data = bundle[offset:offset + item['bytes']]
    assert hashlib.sha256(data).hexdigest() == item['sha256']
    for directory in ('/boot', '/home/debian/current-bundle'):
        copies[str(Path(directory) / item['file'])] = data
config = gzip.decompress(Path('/proc/config.gz').read_bytes())
assert hashlib.sha256(config).hexdigest() == 'ba01595843f6ca6b37f058a89fd9ec0db4cc0bb38031a1523be44cc6f54095f3'
copies['/boot/kernel.config'] = config
copies['/boot/config-7.3.3-tzx-a523-accel1'] = config
copies['/home/debian/installed-bundle.json'] = manifest_path.read_bytes()
backup = Path('/root/tzx-recovery/cpufreq-boot-mirrors')
backup.mkdir(parents=True, exist_ok=False)
before = {}
for name, data in copies.items():
    path = Path(name)
    assert not path.is_symlink()
    if path.exists():
        saved = backup / name.lstrip('/')
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(path.read_bytes())
        before[name] = hashlib.sha256(saved.read_bytes()).hexdigest()
    else:
        before[name] = None
(backup / 'before.json').write_text(json.dumps(before, indent=2) + '\n')
for name, data in copies.items():
    path = Path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.verified-new')
    with temporary.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    assert path.read_bytes() == data
state_path = Path('/var/lib/tzx/cpufreq-framework-installed.json')
state = json.loads(state_path.read_text())
state.update(state='framework_5_boot_and_manual_governor_verified',
             mirror_sha256={name: hashlib.sha256(data).hexdigest() for name, data in copies.items()})
state_path.write_text(json.dumps(state, indent=2) + '\n')
os.sync()
print('CPUFREQ_SPLIT_SLOT_BOOT_AND_NINE_MIRRORS_VERIFIED', json.dumps(state), flush=True)
