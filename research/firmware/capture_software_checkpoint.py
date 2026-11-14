"""Read only the host's explicit runtime list and the exact installed boot bundle."""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tarfile

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#3 ' in os.uname().version
assert not Path('/sys/module/panfrost').exists()
assert not Path('/var/lib/tzx/gpu-qualified').exists()
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert subprocess.check_output(['systemctl', 'is-active', 'lightdm'], text=True).strip() == 'active'
overrides = json.loads(Path('/usr/local/lib/tzx-accel/overrides.json').read_text())
assert '--config=' not in overrides['lightdm.service']
request = json.loads(Path('/home/debian/software-checkpoint-request.json').read_text())
bundle = request['bundle']
with open('/dev/mmcblk0', 'rb', buffering=0) as emmc:
    emmc.seek(4096*512)
    data = emmc.read(bundle['bytes'])
assert hashlib.sha256(data).hexdigest() == bundle['sha256']
output = Path('/home/debian/software-clockfix-keys-checkpoint.tar.gz')
assert not output.exists()
files = {}

def add(package, name, contents, mode):
    member = tarfile.TarInfo(name)
    member.size = len(contents)
    member.mode = mode
    package.addfile(member, io.BytesIO(contents))
    files[name] = {'bytes': len(contents), 'sha256': hashlib.sha256(contents).hexdigest(),
                   'mode': oct(mode)}

with tarfile.open(output, 'w:gz') as package:
    add(package, 'linux-bundle.bin', data, 0o644)
    add(package, 'linux-bundle.json', (json.dumps(bundle, indent=2)+'\n').encode(), 0o644)
    for name in request['paths']:
        assert name.startswith(('boot/config-', 'etc/', 'lib/', 'usr/local/', 'usr/share/drirc.d/',
                                'usr/lib/systemd/system-generators/tzx-'))
        assert '..' not in Path(name).parts and not Path(name).is_absolute()
        path = Path('/')/name
        assert path.is_file(), name
        add(package, 'runtime/'+name, path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
    record = {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'kernel': os.uname().version, 'rootfs_included': False,
              'gpu_qualified': False, 'boot_renderer': 'software', 'files': files}
    contents = (json.dumps(record, indent=2)+'\n').encode()
    member = tarfile.TarInfo('FILES.json')
    member.size = len(contents)
    member.mode = 0o644
    package.addfile(member, io.BytesIO(contents))
output.chmod(0o644)
print('SOFTWARE_CHECKPOINT_CAPTURED', output.stat().st_size,
      hashlib.sha256(output.read_bytes()).hexdigest(), len(files), flush=True)
