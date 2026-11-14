"""Retrieve the small screen startup checkpoint and verify every member."""
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
import subprocess
import tarfile

root=Path(__file__).resolve().parents[1]
log=(root/'evidence/screen-fast-checkpoint-capture.txt').read_text(encoding='utf-8')
match=re.search(r'SCREEN_FAST_INSTALLED_CHECKPOINT_CREATED (\{.*\})',log)
assert match
created=json.loads(match[1])
assert created['bytes']<1024*1024
assert created['path']=='/home/debian/screen-fast-installed-checkpoint.tar.gz'
target=root/'build/screen-fast-installed-checkpoint.tar.gz'
assert not target.exists()
subprocess.run(['scp','-q','-l','4000','-i',str(root/'private/tzx-host-ed25519'),
    '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
    '-o','UserKnownHostsFile='+str(root/'private/tablet_known_hosts'),
    'debian@192.168.77.2:'+created['path'],str(target)],check=True,timeout=45)
sha=lambda b:hashlib.sha256(b).hexdigest()
assert target.stat().st_size==created['bytes'] and sha(target.read_bytes())==created['sha256']
with tarfile.open(target) as archive:
    members=archive.getmembers()
    manifest=json.load(archive.extractfile('MANIFEST.json'))
    assert len(members)==len({m.name for m in members})
    assert {m.name for m in members}==set(manifest['files'])|{'MANIFEST.json'}
    for item in members:
        path=PurePosixPath(item.name)
        assert item.isfile() and not path.is_absolute() and '..' not in path.parts
    for name,digest in manifest['files'].items():
        assert sha(archive.extractfile(name).read())==digest,name
        assert archive.getmember(name).mode==manifest['modes'][name],name
    user=archive.extractfile('var/lib/tzx/screen-fast-user-confirmed.json').read()
    (root/'evidence/screen-fast-user-observations.json').write_bytes(user)
    for name in ('screen-fast-final-qualified','screen-fast-installed','screen-fast-key-on-qualified'):
        (root/'evidence'/(name+'.json')).write_bytes(archive.extractfile('var/lib/tzx/'+name+'.json').read())
assert manifest['normal_reboot_verified'] and manifest['poweroff_key_on_verified']
record=dict(manifest,archive_sha256=created['sha256'],archive_bytes=created['bytes'],every_member_verified=True)
(root/'build/screen-fast-installed-checkpoint.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('SCREEN_FAST_INSTALLED_ALL_MEMBERS_AND_MODES_VERIFIED',json.dumps(created),flush=True)
