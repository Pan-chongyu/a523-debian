"""Capture only the installed WLAN change and its exact rollback files."""
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import time

assert os.geteuid() == 0 and '#4 ' in os.uname().version
cid = Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()
assert cid == '3e01ff55454d20202010209170281b59'
record_path = Path('/var/lib/tzx/wifi-fourbit-installed.json')
record = json.loads(record_path.read_text())
assert record['state'] == 'manual_trials_and_autostart_reboot_verified'
expected = {
    '/usr/local/lib/tzx-peripherals-accel1/tzx_wifi_runtime.ko':
        '313e014683a700cf4157eb08f7136b6af12c938464d0e520690a2db72890f74b',
    '/usr/local/lib/tzx-peripherals-accel1/tzx-wifi-runtime-test.sh':
        '701b4b7663cb8fd80a1ab48c50c7bff9c51f44f2015f9e0e57ef85446f14502a'}
assert record['files'] == expected
backup = Path('/root/tzx-recovery/wifi-fourbit')
before = json.loads((backup / 'before.json').read_text())
assert set(before) == set(expected)
paths = [Path(name) for name in expected] + [record_path]
paths += [backup / name for name in (
    'before.json', 'installed.json', 'rollback.py',
    'tzx_wifi_runtime.ko', 'tzx-wifi-runtime-test.sh')]
contents = {}
for path in paths:
    assert path.is_file() and not path.is_symlink()
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if str(path) in expected:
        assert digest == expected[str(path)]
    if path.name in ('tzx_wifi_runtime.ko', 'tzx-wifi-runtime-test.sh') and path.parent == backup:
        installed_path = '/usr/local/lib/tzx-peripherals-accel1/' + path.name
        assert digest == before[installed_path]['sha256']
    contents[str(path).lstrip('/')] = data
manifest = {'cid': cid, 'kernel': os.uname().release, 'kernel_build': os.uname().version,
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'scope': 'two installed WLAN files, their rollback, and verified metadata; no credentials',
            'files': {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}}
contents['MANIFEST.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
destination = Path('/home/debian/wifi-fourbit-checkpoint.tar.gz')
with destination.open('xb') as output:
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        for name, data in sorted(contents.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            info.mtime = int(time.time())
            archive.addfile(info, io.BytesIO(data))
    output.flush()
    os.fsync(output.fileno())
destination.chmod(0o644)
print('WIFI_FOURBIT_CHECKPOINT_CREATED', json.dumps({
    'path': str(destination), 'bytes': destination.stat().st_size,
    'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
    'files': len(manifest['files']), 'boot_id': manifest['boot_id']}), flush=True)
