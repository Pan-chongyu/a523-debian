"""Retrieve the explicit WLAN snapshot and verify every archive member."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile

root = Path(__file__).resolve().parents[1]
helper = root / 'tools/tablet_ssh.py'
subprocess.run([sys.executable, '-X', 'utf8', str(helper), '--file',
    str(root / 'firmware/capture_wifi_fourbit_checkpoint.py'), '--remote',
    '/home/debian/capture_wifi_fourbit_checkpoint.py'], check=True)
result = subprocess.run([sys.executable, '-X', 'utf8', str(helper), '--root', '--command',
    'python3 /home/debian/capture_wifi_fourbit_checkpoint.py', '--output',
    'wifi-fourbit-checkpoint-capture.txt'], check=True, capture_output=True, text=True, encoding='utf-8')
match = re.search(r'WIFI_FOURBIT_CHECKPOINT_CREATED (\{.*\})', result.stdout)
assert match, result.stdout
created = json.loads(match[1])
private = root / 'private'
destination = root / 'build/wifi-fourbit-checkpoint.tar.gz'
assert not destination.exists()
subprocess.run(['scp', '-i', str(private / 'tzx-host-ed25519'), '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(private / 'tablet_known_hosts'),
    'debian@192.168.77.2:/home/debian/wifi-fourbit-checkpoint.tar.gz', str(destination)],
    check=True, timeout=30)
digest = hashlib.sha256(destination.read_bytes()).hexdigest()
assert digest == created['sha256'] and destination.stat().st_size == created['bytes']
with tarfile.open(destination, 'r:gz') as archive:
    members = archive.getmembers()
    assert len({member.name for member in members}) == len(members)
    assert all(member.isfile() and not PurePosixPath(member.name).is_absolute()
               and '..' not in PurePosixPath(member.name).parts for member in members)
    manifest = json.load(archive.extractfile('MANIFEST.json'))
    assert manifest['cid'] == '3e01ff55454d20202010209170281b59'
    assert {member.name for member in members} == set(manifest['files']) | {'MANIFEST.json'}
    for name, expected in manifest['files'].items():
        assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == expected, name
report = dict(manifest, archive_sha256=digest, archive_bytes=destination.stat().st_size,
              every_member_verified=True)
(root / 'build/wifi-fourbit-checkpoint.json').write_text(json.dumps(report, indent=2) + '\n')
print('WIFI_FOURBIT_CHECKPOINT_RETRIEVED_AND_VERIFIED', json.dumps({
    'sha256': digest, 'files': len(manifest['files']), 'bytes': destination.stat().st_size}))
