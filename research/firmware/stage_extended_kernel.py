"""Install only additive modules and write the inactive boot slot with verification."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

assert os.geteuid()==0
archive=Path('/home/debian/extended-kernel-install.tar.gz')
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='209fc8ddb4cfa9f1c8797f8f00fc269574aeb0e2090447b9f2bc8dba30da708e'
folder=Path('/home/debian/extended-kernel')
with tarfile.open(archive) as tf:
    for member in tf.getmembers():
        assert member.isfile() or member.isdir()
        assert not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
    tf.extractall(folder,filter='data')
receipt={}
for path in (folder/'native').rglob('*.ko'):
    destination=Path('/lib/modules')/os.uname().release/'kernel'/path.relative_to(folder/'native')
    data=path.read_bytes()
    assert not destination.exists() or destination.read_bytes()==data,destination
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(data);destination.chmod(0o644)
    receipt[str(destination)]=hashlib.sha256(data).hexdigest()
subprocess.run(['depmod','-a'],check=True)
(folder/'native-installed.json').write_text(json.dumps(receipt,indent=2)+'\n')
for operation in ('verify','stage','activate'):
    subprocess.run(['python3','/home/debian/install_extended_kernel.py',operation],check=True,timeout=120)
os.sync()
print('EXTENDED_KERNEL_INACTIVE_SLOT_STAGED_SELECTED_AND_ADDITIVE_MODULES_READY',flush=True)
