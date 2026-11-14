"""Archive only one diagnostic library capture, with per-file hashes."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import tarfile

parser = argparse.ArgumentParser()
parser.add_argument('--label', required=True)
args = parser.parse_args()
assert os.geteuid() == 0 and args.label and all(c.isalnum() or c == '-' for c in args.label)
cid = Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()
assert cid == '3e01ff55454d20202010209170281b59'
source = Path('/home/debian/tzx-gpu-debug/pages-'+args.label)
files = sorted(source.iterdir())
assert all(path.is_file() and not path.is_symlink() for path in files)
assert all(path.name in {'baseline.json', 'monitor-maps.txt', 'independent-views.json',
                        'expected.bin', 'changed-cache.bin', 'setup.jsonl', 'changed.json',
                        'direct-after.bin'} or path.name.startswith('page-') and path.suffix == '.bin'
           for path in files)
assert sum(path.stat().st_size for path in files) < 64*1024*1024
data = {path.name: path.read_bytes() for path in files}
changed = json.loads(data['changed.json'])
manifest = {'cid': cid, 'label': args.label, 'captured_boot_id': changed['boot_id'],
            'files': {name: hashlib.sha256(content).hexdigest() for name, content in data.items()}}
output = Path('/home/debian/gpu-'+args.label+'-cache-capture.tar.gz')
with output.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as archive:
    for name, content in dict(data, **{'MANIFEST.json': json.dumps(manifest, indent=2).encode()+b'\n'}).items():
        info = tarfile.TarInfo(name)
        info.size, info.mode = len(content), 0o600
        archive.addfile(info, io.BytesIO(content))
account = pwd.getpwnam('debian')
os.chown(output, account.pw_uid, account.pw_gid)
output.chmod(0o600)
print('GPU_PAGE_CAPTURE_PACKAGED', json.dumps({'path': str(output), 'bytes': output.stat().st_size,
      'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'files': len(data)}), flush=True)
