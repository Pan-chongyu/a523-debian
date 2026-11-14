"""Add only the observed shutdown-order correction to the qualified display."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
ROOT = Path('/var/lib/tzx')
state_path = ROOT/'screen-installed.json'
state_bytes = state_path.read_bytes()
state = json.loads(state_bytes)
assert state['state'] == 'manual_display_and_actual_autostart_verified'
assert state['verified_boot_id'] == BOOT
runtime = Path('/usr/local/lib/tzx-screen/runtime.py')
old = runtime.read_bytes()
assert hashlib.sha256(old).hexdigest() == '6f0c2671ce6ed129e5ad868ce8966d24bb3f558516fbda3928da2dee6869cbf9'
manifest_bytes = Path('/home/debian/screen-brightness-FILES.json').read_bytes()
manifest = json.loads(manifest_bytes)
package = Path('/home/debian/screen-runtime-brightness-save.tar.gz').read_bytes()
assert hashlib.sha256(package).hexdigest() == manifest['package_sha256']
with tarfile.open(fileobj=io.BytesIO(package), mode='r:gz') as archive:
    assert set(archive.getnames()) == set(state['files']) == set(manifest['files'])
    data = archive.extractfile(str(runtime).lstrip('/')).read()
    for name, item in state['files'].items():
        installed = (Path('/')/name).read_bytes()
        assert hashlib.sha256(installed).hexdigest() == item['sha256'], name
        if name != str(runtime).lstrip('/'):
            assert archive.extractfile(name).read() == installed, name
assert hashlib.sha256(data).hexdigest() == manifest['files'][str(runtime).lstrip('/')]['sha256']
compile(data, str(runtime), 'exec')
backup = Path('/root/tzx-recovery/screen-brightness-save-v2')
backup.mkdir()


def atomic(path, content, mode=0o600):
    tmp = path.with_name(path.name+'.save-new')
    with tmp.open('wb') as f:
        f.write(content)
        os.fchmod(f.fileno(), mode)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)


for name, content in {'old-runtime.py': old, 'before-state.json': state_bytes,
                      'new-package.tar.gz': package, 'new-FILES.json': manifest_bytes,
                      'upgrader.py': Path(__file__).read_bytes()}.items():
    atomic(backup/name, content)
atomic(runtime, data, 0o644)
state['files'] = manifest['files']
state['package_sha256'] = manifest['package_sha256']
state['brightness_save_revision'] = 2
state['brightness_fix_installed_boot_id'] = BOOT
state['brightness_persistence'] = 'pending_actual_reboot'
atomic(state_path, (json.dumps(state, indent=2)+'\n').encode())
# Exercise the unchanged systemd save API with the live backlight available.
subprocess.run(['/usr/lib/systemd/systemd-backlight', 'save', 'backlight:tzx-panel'], check=True, timeout=15)
os.sync()
print('TZX_SCREEN_BRIGHTNESS_SAVE_ORDER_PATCH_INSTALLED', flush=True)
