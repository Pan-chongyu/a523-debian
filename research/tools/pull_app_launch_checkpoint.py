"""Fetch only the app overlay and verify all archive members and modes."""
import hashlib,json,re,subprocess,tarfile
from pathlib import Path,PurePosixPath
root=Path(__file__).resolve().parents[1]
match=re.search(r'APP_LAUNCH_INSTALLED_CHECKPOINT_CREATED (\{.*\})',
    (root/'evidence/app-launch-checkpoint-capture.txt').read_text(encoding='utf-8'));assert match
created=json.loads(match[1]);assert created['bytes']<3*1024*1024
assert created['path']=='/home/debian/app-launch-installed-checkpoint.tar.gz'
target=root/'build/app-launch-installed-checkpoint.tar.gz';assert not target.exists()
subprocess.run(['scp','-q','-i',str(root/'private/tzx-host-ed25519'),'-o','BatchMode=yes',
    '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(root/'private/tablet_known_hosts'),
    'debian@192.168.77.2:'+created['path'],str(target)],check=True,timeout=45)
sha=lambda b:hashlib.sha256(b).hexdigest()
assert target.stat().st_size==created['bytes'] and sha(target.read_bytes())==created['sha256']
with tarfile.open(target) as archive:
    members=archive.getmembers();manifest=json.load(archive.extractfile('MANIFEST.json'))
    assert len(members)==len({m.name for m in members})
    assert {m.name for m in members}==set(manifest['files'])|{'MANIFEST.json'}
    for item in members:
        path=PurePosixPath(item.name);assert item.isfile() and not path.is_absolute() and '..' not in path.parts
    for name,digest in manifest['files'].items():
        assert sha(archive.extractfile(name).read())==digest,name
        assert archive.getmember(name).mode==manifest['modes'][name],name
    for name in ('app-launch-final-qualified','app-launch-controls-qualified','app-cache-comparison-qualified'):
        (root/'evidence'/(name+'.json')).write_bytes(archive.extractfile('var/lib/tzx/'+name+'.json').read())
record=dict(manifest,archive_sha256=created['sha256'],archive_bytes=created['bytes'],every_member_verified=True)
(root/'build/app-launch-installed-checkpoint.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('APP_LAUNCH_INSTALLED_EVERY_MEMBER_AND_MODE_VERIFIED',json.dumps(created),flush=True)
