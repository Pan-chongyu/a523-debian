"""Retrieve the actual installed advanced profile, verifying every archived byte."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import time

root = Path(__file__).resolve().parents[1]
stem = 'advanced-performance-installed-checkpoint'
helper = [sys.executable, '-X', 'utf8', str(root/'tools/tablet_ssh.py')]
capture_log = root/'evidence'/(stem+'-capture.txt')
match = re.search(r'ADVANCED_INSTALLED_CHECKPOINT_CREATED (\{.*\})', capture_log.read_text(encoding='utf-8')) if capture_log.exists() else None
if not match:
    subprocess.run(helper+['--file', str(root/'firmware/capture_advanced_checkpoint.py'),
                          '--remote', '/home/debian/capture_advanced_checkpoint.py'], check=True)
    result = subprocess.run(helper+['--root', '--command', 'python3 /home/debian/capture_advanced_checkpoint.py',
        '--output', stem+'-capture.txt', '--timeout', '120'], check=True, capture_output=True, text=True, encoding='utf-8')
    match = re.search(r'ADVANCED_INSTALLED_CHECKPOINT_CREATED (\{.*\})', result.stdout)
created = json.loads(match[1])
print('INSTALLED_SNAPSHOT_CREATED', json.dumps(created), flush=True)
destination = root/'build'/(stem+'.tar.gz')
subprocess.run(helper+['--file', str(root/'firmware/chunk_advanced_checkpoint.py'),
                      '--remote', '/home/debian/chunk_advanced_checkpoint.py'], check=True)
result = subprocess.run(helper+['--root', '--command', 'python3 /home/debian/chunk_advanced_checkpoint.py',
    '--output', stem+'-chunks.txt', '--timeout', '60'], check=True, capture_output=True, text=True, encoding='utf-8')
chunks = json.loads(result.stdout)
assert chunks['sha256'] == created['sha256'] and chunks['bytes'] == created['bytes']
parts = root/'build'/(stem+'.parts')
parts.mkdir(exist_ok=True)
for i, item in enumerate(chunks['chunks']):
    local = parts/item['name']
    assert re.fullmatch(r'[0-9]{3}\.part', item['name'])
    for attempt in range(4):
        if local.exists() and local.stat().st_size == item['bytes'] and hashlib.sha256(local.read_bytes()).hexdigest() == item['sha256']:
            break
        result = subprocess.run(['scp', '-l', '4000', '-i', str(root/'private/tzx-host-ed25519'),
            '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'UserKnownHostsFile='+str(root/'private/tablet_known_hosts'),
            'debian@192.168.77.2:'+chunks['folder']+'/'+item['name'], str(local)], timeout=40, capture_output=True)
        if result.returncode:
            print('CHUNK_TRANSFER_RETRY', i, attempt+1, flush=True)
        time.sleep(.2)
    assert local.stat().st_size == item['bytes'] and hashlib.sha256(local.read_bytes()).hexdigest() == item['sha256'], item['name']
    if i % 8 == 0 or i+1 == len(chunks['chunks']):
        print('CHUNKS_VERIFIED', i+1, 'of', len(chunks['chunks']), flush=True)
with destination.open('wb') as output:
    for item in chunks['chunks']:
        output.write((parts/item['name']).read_bytes())
assert hashlib.sha256(destination.read_bytes()).hexdigest() == created['sha256']
assert destination.stat().st_size == created['bytes']
with tarfile.open(destination) as archive:
    members = archive.getmembers()
    assert all(m.isfile() and not PurePosixPath(m.name).is_absolute()
               and '..' not in PurePosixPath(m.name).parts for m in members)
    manifest = json.load(archive.extractfile('MANIFEST.json'))
    assert {m.name for m in members} == set(manifest['files']) | {'MANIFEST.json'}
    assert len({m.name for m in members}) == len(members)
    for name, digest in manifest['files'].items():
        assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == digest, name
        assert archive.getmember(name).mode == manifest['modes'][name]
    for name, link in manifest['symlinks'].items():
        assert not PurePosixPath(link).is_absolute() and '..' not in PurePosixPath(link).parts
        assert str(PurePosixPath(name).parent/link) in manifest['files']
record = dict(manifest, archive_sha256=created['sha256'], archive_bytes=created['bytes'], every_member_verified=True)
(root/'build'/(stem+'.json')).write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
print('ADVANCED_CHECKPOINT_RETRIEVED_ALL_MEMBERS_VERIFIED', json.dumps(created), flush=True)
