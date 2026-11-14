"""Package board-measured volume/power keys with an exact CID/hash guard."""
import hashlib
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
out = root/'build/tablet-keys'
stage = out/'runtime'
release = '7.3.3-tzx-a523-accel1'
files = {}
for directory, name in [('lradc-keys', 'tzx_lradc_keyboard.ko'), ('power-key', 'tzx_power_key.ko')]:
    data = (root/'build'/directory/name).read_bytes()
    assert (release+' ').encode() in data
    files['lib/modules/'+release+'/extra/'+name] = data
prefix = 'usr/local/lib/tzx-tablet-keys/'
files[prefix+'MODULES.sha256'] = ''.join(hashlib.sha256(data).hexdigest()+'  /'+name+'\n'
    for name, data in sorted(files.items())).encode()
files[prefix+'tzx-tablet-keys'] = (root/'firmware/tzx-tablet-keys').read_bytes()
files['etc/systemd/system/tzx-tablet-keys.service'] = (root/'firmware/tzx-tablet-keys.service').read_bytes()
manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
for name, data in files.items():
    path = stage/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
(stage/'FILES.json').write_text(json.dumps(manifest, indent=2)+'\n')
installer = '''import hashlib,json,os,subprocess
from pathlib import Path
assert os.geteuid()==0 and os.uname().release=='7.3.3-tzx-a523-accel1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
stage=Path(__file__).resolve().parent
files=json.loads((stage/'FILES.json').read_text())
for name,digest in files.items():
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    assert name.startswith(('lib/modules/7.3.3-tzx-a523-accel1/extra/tzx_',
        'usr/local/lib/tzx-tablet-keys/','etc/systemd/system/tzx-tablet-keys.service'))
    assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==digest
for name,digest in files.items():
    target=Path('/')/name
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.tzx-new')
    with temporary.open('wb') as stream:
        stream.write((stage/name).read_bytes());stream.flush();os.fsync(stream.fileno())
    temporary.chmod(0o644);temporary.replace(target)
    assert hashlib.sha256(target.read_bytes()).hexdigest()==digest
subprocess.run(['depmod','-a',os.uname().release],check=True)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemd-analyze','--man=no','verify','tzx-tablet-keys.service'],check=True)
subprocess.run(['systemctl','enable','--now','tzx-tablet-keys.service'],check=True)
os.sync()
print('TABLET_KEYS_INSTALLED_HASH_VERIFIED',len(files))
'''
compile(installer, 'install.py', 'exec')
(stage/'install.py').write_text(installer, newline='\n')
archive = out/'tablet-keys.tar.gz'
with tarfile.open(archive, 'w:gz') as package:
    for name in sorted([*files, 'FILES.json', 'install.py']):
        package.add(stage/name, arcname=name, recursive=False)
(out/'tablet-keys.json').write_text(json.dumps({'files':manifest,
    'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
    'volume_user_verified':True,'power_menu_user_verified':False,'autostart_reboot_verified':False},indent=2)+'\n')
print('TABLET_KEYS_PACKAGED',len(files),archive.stat().st_size)
