"""Split only the named recovery archive for independently verified USB transfers."""
import hashlib
import json
from pathlib import Path

source = Path('/home/debian/advanced-performance-installed-checkpoint.tar.gz')
folder = Path('/home/debian/advanced-checkpoint-chunks')
folder.mkdir(mode=0o755, exist_ok=True)
assert not folder.is_symlink()
data = source.read_bytes()
sha = lambda value: hashlib.sha256(value).hexdigest()
assert sha(data) == '16cd5bc7b43ab16dbeab21a2718e366e3365e2d5e48bfce19a339e342cf3b7c3'
chunks = []
for i, offset in enumerate(range(0, len(data), 1024*1024)):
    part = data[offset:offset+1024*1024]
    target = folder/f'{i:03}.part'
    assert not target.is_symlink()
    if target.exists():
        assert target.read_bytes() == part
    else:
        target.write_bytes(part)
    target.chmod(0o644)
    chunks.append(dict(name=target.name, bytes=len(part), sha256=sha(part)))
print(json.dumps(dict(folder=str(folder), bytes=len(data), sha256=sha(data), chunks=chunks)))
