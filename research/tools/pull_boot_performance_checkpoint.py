"""Fetch the small boot delta and verify every archived byte and permission."""
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
import subprocess
import tarfile
root=Path(__file__).resolve().parents[1]
log=(root/'evidence/boot-performance-delta-capture.txt').read_text(encoding='utf-8')
match=re.search(r'BOOT_PERFORMANCE_DELTA_CHECKPOINT_CREATED (\{.*\})',log);assert match
created=json.loads(match[1]);assert created['bytes']<1024*1024
assert created['path']=='/home/debian/boot-performance-installed-checkpoint-v2.tar.gz'
target=root/'build/boot-performance-installed-checkpoint-v2.tar.gz';assert not target.exists()
subprocess.run(['scp','-q','-l','4000','-i',str(root/'private/tzx-host-ed25519'),
    '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
    '-o','UserKnownHostsFile='+str(root/'private/tablet_known_hosts'),
    'debian@192.168.77.2:'+created['path'],str(target)],check=True,timeout=45)
sha=lambda b:hashlib.sha256(b).hexdigest()
assert target.stat().st_size==created['bytes'] and sha(target.read_bytes())==created['sha256']
with tarfile.open(target) as archive:
    members=archive.getmembers();manifest=json.load(archive.extractfile('MANIFEST.json'))
    assert len(members)==len({m.name for m in members})
    assert {m.name for m in members}==set(manifest['files'])|{'MANIFEST.json'}
    for m in members:
        p=PurePosixPath(m.name)
        assert m.isfile() and not p.is_absolute() and '..' not in p.parts
    for name,digest in manifest['files'].items():
        assert sha(archive.extractfile(name).read())==digest,name
        assert archive.getmember(name).mode==manifest['modes'][name]
assert manifest['normal_reboot_verified'] and manifest['poweroff_key_on_verified']
record=dict(manifest,archive_sha256=created['sha256'],archive_bytes=created['bytes'],every_member_verified=True)
(root/'build/boot-performance-installed-checkpoint-v2.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('BOOT_PERFORMANCE_INSTALLED_DELTA_ALL_MEMBERS_VERIFIED',json.dumps(created),flush=True)
