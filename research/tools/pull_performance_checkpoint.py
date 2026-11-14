"""Retrieve the scoped actual-performance snapshot and verify every member."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--storage',action='store_true')
args = parser.parse_args()
stem = 'performance-storage-installed-checkpoint' if args.storage else 'performance-installed-checkpoint'
helper = [sys.executable, '-X', 'utf8', str(root/'tools/tablet_ssh.py')]
subprocess.run(helper+['--file', str(root/'firmware/capture_performance_checkpoint.py'),
                      '--remote', '/home/debian/capture_performance_checkpoint.py'], check=True)
command = 'python3 /home/debian/capture_performance_checkpoint.py'+(' --storage' if args.storage else '')
result = subprocess.run(helper+['--root', '--command', command,
    '--output', stem+'-capture.txt', '--timeout', '60'], check=True,
    capture_output=True, text=True, encoding='utf-8')
created = json.loads(re.search(r'PERFORMANCE_INSTALLED_CHECKPOINT_CREATED (\{.*\})', result.stdout)[1])
destination = root/('build/'+stem+'.tar.gz')
assert not destination.exists()
subprocess.run(['scp', '-l', '8000', '-i', str(root/'private/tzx-host-ed25519'),
    '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
    '-o', 'UserKnownHostsFile='+str(root/'private/tablet_known_hosts'),
    'debian@192.168.77.2:'+created['path'], str(destination)], check=True, timeout=80)
assert hashlib.sha256(destination.read_bytes()).hexdigest() == created['sha256']
assert destination.stat().st_size == created['bytes']
with tarfile.open(destination) as archive:
    members = archive.getmembers()
    assert all(m.isfile() and not PurePosixPath(m.name).is_absolute()
               and '..' not in PurePosixPath(m.name).parts for m in members)
    manifest = json.load(archive.extractfile('MANIFEST.json'))
    assert {m.name for m in members} == set(manifest['files']) | {'MANIFEST.json'}
    assert len({m.name for m in members}) == len(members)
    for name,digest in manifest['files'].items():
        assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == digest, name
record = dict(manifest, archive_sha256=created['sha256'], archive_bytes=created['bytes'], every_member_verified=True)
(root/('build/'+stem+'.json')).write_text(json.dumps(record, indent=2)+'\n')
print('PERFORMANCE_CHECKPOINT_RETRIEVED_ALL_MEMBERS_VERIFIED', json.dumps(created))
