"""Retrieve one frozen capture and check every archive member against its manifest."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile

parser = argparse.ArgumentParser()
parser.add_argument('label')
args = parser.parse_args()
assert re.fullmatch(r'[a-zA-Z0-9-]+', args.label)
root = Path(__file__).resolve().parents[1]
helper = root/'tools/tablet_ssh.py'
destination = root/('build/gpu-'+args.label+'-cache-capture.tar.gz')
assert not destination.exists()
subprocess.run([sys.executable, '-X', 'utf8', str(helper), '--file',
    str(root/'firmware/package_gpu_page_capture.py'), '--remote',
    '/home/debian/package_gpu_page_capture.py'], check=True)
result = subprocess.run([sys.executable, '-X', 'utf8', str(helper), '--root', '--command',
    'python3 /home/debian/package_gpu_page_capture.py --label '+args.label,
    '--timeout', '30', '--output', args.label+'-capture-packaged.txt'],
    capture_output=True, text=True, encoding='utf8', check=True)
match = re.search(r'GPU_PAGE_CAPTURE_PACKAGED (\{.*\})', result.stdout)
assert match, result.stdout
record = json.loads(match[1])
assert record['path'] == '/home/debian/gpu-'+args.label+'-cache-capture.tar.gz'
private = root/'private'
subprocess.run(['scp', '-l', '4000', '-i', str(private/'tzx-host-ed25519'),
    '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
    '-o', 'UserKnownHostsFile='+str(private/'tablet_known_hosts'),
    'debian@192.168.77.2:'+record['path'], str(destination)], check=True, timeout=60)
assert destination.stat().st_size == record['bytes']
assert hashlib.sha256(destination.read_bytes()).hexdigest() == record['sha256']
with tarfile.open(destination) as archive:
    members = archive.getmembers()
    assert len({m.name for m in members}) == len(members)
    assert all(m.isfile() and not PurePosixPath(m.name).is_absolute()
               and '..' not in PurePosixPath(m.name).parts for m in members)
    manifest = json.load(archive.extractfile('MANIFEST.json'))
    assert manifest['label'] == args.label
    assert manifest['cid'] == '3e01ff55454d20202010209170281b59'
    assert set(m.name for m in members) == set(manifest['files']) | {'MANIFEST.json'}
    for name, digest in manifest['files'].items():
        assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == digest, name
report = dict(record, every_archive_member_verified=True, manifest=manifest)
destination.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf8')
print('GPU_CAPTURE_HOST_FULL_VERIFICATION_PASS', json.dumps(report), flush=True)
