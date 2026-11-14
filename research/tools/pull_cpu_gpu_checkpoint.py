"""Retrieve the actual CPU/GPU snapshot in verified, bounded USB transfers."""
import hashlib,json,re,subprocess,sys,tarfile,time
from pathlib import Path,PurePosixPath
root=Path(__file__).resolve().parents[1]
stem='cpu-gpu-native-installed-checkpoint'
helper=[sys.executable,'-X','utf8',str(root/'tools/tablet_ssh.py')]
log=(root/'evidence/cpu-gpu-native-checkpoint-capture.txt').read_text(encoding='utf-8')
match=re.search(r'CPU_GPU_INSTALLED_CHECKPOINT_CREATED (\{.*\})',log)
assert match,log
created=json.loads(match[1])
result=subprocess.run(helper+['--root','--command','python3 /home/debian/chunk_cpu_gpu_checkpoint.py '+created['sha256'],
    '--output','cpu-gpu-native-checkpoint-chunks.txt','--timeout','60'],check=True,capture_output=True,text=True,encoding='utf-8')
chunks=json.loads(result.stdout)
assert chunks['bytes']==created['bytes'] and chunks['sha256']==created['sha256']
assert chunks['folder']=='/home/debian/cpu-gpu-native-checkpoint-chunks'
parts=root/'build'/(stem+'.parts');parts.mkdir(exist_ok=True)
sha=lambda b:hashlib.sha256(b).hexdigest()
for i,item in enumerate(chunks['chunks']):
    assert re.fullmatch('[0-9]{3}\.part',item['name'])
    target=parts/item['name']
    for attempt in range(4):
        if target.is_file() and target.stat().st_size==item['bytes'] and sha(target.read_bytes())==item['sha256']:break
        result=subprocess.run(['scp','-q','-l','4000','-i',str(root/'private/tzx-host-ed25519'),
            '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
            '-o','UserKnownHostsFile='+str(root/'private/tablet_known_hosts'),
            'debian@192.168.77.2:'+chunks['folder']+'/'+item['name'],str(target)],capture_output=True,timeout=40)
        if result.returncode:print('CHUNK_RETRY',i,attempt+1,flush=True)
        time.sleep(.2)
    assert target.is_file() and target.stat().st_size==item['bytes'] and sha(target.read_bytes())==item['sha256']
    if i%8==0 or i+1==len(chunks['chunks']):print('CPU_GPU_CHUNKS_VERIFIED',i+1,len(chunks['chunks']),flush=True)
destination=root/'build'/(stem+'.tar.gz')
assert not destination.exists()
with destination.open('wb') as stream:
    for item in chunks['chunks']:stream.write((parts/item['name']).read_bytes())
assert destination.stat().st_size==created['bytes'] and sha(destination.read_bytes())==created['sha256']
with tarfile.open(destination) as archive:
    members=archive.getmembers();manifest=json.load(archive.extractfile('MANIFEST.json'))
    assert len(members)==len({m.name for m in members})
    assert {m.name for m in members}==set(manifest['files'])|{'MANIFEST.json'}
    for member in members:
        path=PurePosixPath(member.name)
        assert member.isfile() and not path.is_absolute() and '..' not in path.parts
    for name,digest in manifest['files'].items():
        assert sha(archive.extractfile(name).read())==digest,name
        assert archive.getmember(name).mode==manifest['modes'][name]
assert manifest['profile']=='cpu-gpu-native-20261113' and manifest['normal_reboot_verified']
record=dict(manifest,archive_bytes=created['bytes'],archive_sha256=created['sha256'],every_member_verified=True)
(root/'build'/(stem+'.json')).write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('CPU_GPU_INSTALLED_CHECKPOINT_ALL_MEMBERS_VERIFIED',json.dumps(created),flush=True)
