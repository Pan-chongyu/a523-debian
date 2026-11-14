"""Fetch and verify every member of the real installed performance checkpoint."""
import hashlib,json,re,subprocess,tarfile
from pathlib import Path,PurePosixPath
root=Path(__file__).resolve().parents[1]
match=re.search(r'MAX_PERFORMANCE_INSTALLED_CHECKPOINT_CREATED (\{.*\})',(root/'evidence/performance-mode-checkpoint-capture.txt').read_text(encoding='utf-8'));assert match
created=json.loads(match[1]);assert created['bytes']<8*1024*1024
assert created['path']=='/home/debian/max-performance-installed-checkpoint.tar.gz'
target=root/'build/max-performance-installed-checkpoint.tar.gz';assert not target.exists()
subprocess.run(['scp','-q','-i',str(root/'private/tzx-host-ed25519'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
    '-o','UserKnownHostsFile='+str(root/'private/tablet_known_hosts'),'debian@192.168.77.2:'+created['path'],str(target)],check=True,timeout=45)
sha=lambda data:hashlib.sha256(data).hexdigest()
assert target.stat().st_size==created['bytes'] and sha(target.read_bytes())==created['sha256']
with tarfile.open(target) as archive:
    members=archive.getmembers();manifest=json.load(archive.extractfile('MANIFEST.json'))
    assert len(members)==len({m.name for m in members})==len(manifest['files'])+1
    assert {m.name for m in members}==set(manifest['files'])|{'MANIFEST.json'}
    for member in members:
        path=PurePosixPath(member.name);assert member.isfile() and not path.is_absolute() and '..' not in path.parts
    for name,digest in manifest['files'].items():
        assert sha(archive.extractfile(name).read())==digest,name
        assert archive.getmember(name).mode==manifest['modes'][name],name
    for name in ('performance-mode-final-qualified','boot-cpu-performance-qualified','performance-mode-caps-qualified','performance-mode-idle-qualified'):
        (root/'evidence'/(name+'.json')).write_bytes(archive.extractfile('var/lib/tzx/'+name+'.json').read())
record=dict(manifest,archive_sha256=created['sha256'],archive_bytes=created['bytes'],every_member_verified=True)
(root/'build/max-performance-installed-checkpoint.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('MAX_PERFORMANCE_INSTALLED_EVERY_MEMBER_AND_MODE_VERIFIED',json.dumps(created),flush=True)
