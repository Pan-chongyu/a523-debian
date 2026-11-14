"""Fetch the actual installed splash and verify every archived file and mode."""
import hashlib,json,re,subprocess,tarfile
from pathlib import Path,PurePosixPath
root=Path(__file__).resolve().parents[1]
match=re.search(r'BOOT_LOGO_INSTALLED_CHECKPOINT_CREATED (\{.*\})',
    (root/'evidence/boot-logo-checkpoint-capture.txt').read_text(encoding='utf-8'));assert match
created=json.loads(match[1]);assert created['bytes']<32*1024*1024
assert created['path']=='/home/debian/boot-logo-installed-checkpoint.tar.gz'
sha=lambda data:hashlib.sha256(data).hexdigest()
target=root/'build/boot-logo-installed-checkpoint.tar.gz'
transfer_log=[]
if target.exists() and (target.stat().st_size!=created['bytes'] or sha(target.read_bytes())!=created['sha256']):
    partial=target.with_name('boot-logo-checkpoint-default-rate-incomplete.tmp')
    assert partial.parent.resolve()==(root/'build').resolve() and not partial.exists()
    transfer_log.append(dict(result='incomplete-default-rate-transfer',bytes=target.stat().st_size,
                             sha256=sha(target.read_bytes())))
    target.replace(partial)
for attempt in range(3):
    if target.exists() and target.stat().st_size==created['bytes'] and sha(target.read_bytes())==created['sha256']:break
    temporary=target.with_name('boot-logo-checkpoint-download-%d.tmp'%attempt)
    assert not temporary.exists()
    result=subprocess.run(['scp','-q','-l','4000','-i',str(root/'private/tzx-host-ed25519'),
        '-o','BatchMode=yes','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
        '-o','UserKnownHostsFile='+str(root/'private/tablet_known_hosts'),
        'debian@192.168.77.2:'+created['path'],str(temporary)],capture_output=True,timeout=90)
    valid=temporary.exists() and temporary.stat().st_size==created['bytes'] and sha(temporary.read_bytes())==created['sha256']
    transfer_log.append(dict(attempt=attempt+1,limit_kbit_s=4000,exit_code=result.returncode,
        complete_sha256_match=valid,bytes=temporary.stat().st_size if temporary.exists() else 0))
    (root/'evidence/boot-logo-checkpoint-transfers.json').write_text(json.dumps(transfer_log,indent=2)+'\n')
    if valid:temporary.replace(target);break
assert target.stat().st_size==created['bytes'] and sha(target.read_bytes())==created['sha256']
with tarfile.open(target) as archive:
    members=archive.getmembers();manifest=json.load(archive.extractfile('MANIFEST.json'))
    assert len(members)==len({m.name for m in members})==len(manifest['files'])+1
    assert {m.name for m in members}==set(manifest['files'])|{'MANIFEST.json'}
    for member in members:
        path=PurePosixPath(member.name)
        assert member.isfile() and not path.is_absolute() and '..' not in path.parts
    for name,digest in manifest['files'].items():
        assert sha(archive.extractfile(name).read())==digest,name
        assert archive.getmember(name).mode==manifest['modes'][name],name
    for name in ('boot-logo-qualified','boot-logo-installed','boot-logo-stage','boot-panel-installed',
                 'cpu-gpu-integration-qualified'):
        (root/'evidence'/(name+'.json')).write_bytes(archive.extractfile('var/lib/tzx/'+name+'.json').read())
    (root/'build/boot-logo/loader.toc0.json').write_bytes(
        archive.extractfile('home/debian/boot-logo/loader.toc0.json').read())
record=dict(manifest,archive_sha256=created['sha256'],archive_bytes=created['bytes'],every_member_verified=True)
(root/'build/boot-logo-installed-checkpoint.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('BOOT_LOGO_INSTALLED_EVERY_MEMBER_AND_MODE_VERIFIED',json.dumps(created),flush=True)
