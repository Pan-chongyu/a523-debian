"""Split the named CPU/GPU snapshot, checking the caller's complete-file pin."""
import hashlib,json,re,sys
from pathlib import Path
assert len(sys.argv)==2 and re.fullmatch('[0-9a-f]{64}',sys.argv[1])
source=Path('/home/debian/cpu-gpu-native-installed-checkpoint.tar.gz')
folder=Path('/home/debian/cpu-gpu-native-checkpoint-chunks')
folder.mkdir(mode=0o755,exist_ok=True)
assert not folder.is_symlink()
data=source.read_bytes();sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(data)==sys.argv[1]
chunks=[]
for i,offset in enumerate(range(0,len(data),1024*1024)):
    part=data[offset:offset+1024*1024];target=folder/('%03d.part'%i)
    assert not target.is_symlink()
    if target.exists():assert target.read_bytes()==part
    else:target.write_bytes(part)
    target.chmod(0o644)
    chunks.append(dict(name=target.name,bytes=len(part),sha256=sha(part)))
print(json.dumps(dict(folder=str(folder),bytes=len(data),sha256=sha(data),chunks=chunks)))
