"""Retrieve and independently verify the actual trained-DRAM/GPU checkpoint."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--with-cooling', action='store_true')
parser.add_argument('--verify-existing', action='store_true')
parser.add_argument('--download-existing', action='store_true')
parser.add_argument('--bandwidth-kbit', type=int)
parser.add_argument('--name', choices=('dram-gpu-cooling-v2-installed-checkpoint',
                                     'screen-power-audio-installed-checkpoint',
                                     'screen-vblank-installed-checkpoint',
                                     'screen-doublebuffer-installed-checkpoint',
                                     'screen-standby-installed-checkpoint',
                                     'screen-poweron-installed-checkpoint'))
args = parser.parse_args()
assert not (args.verify_existing and args.download_existing)
assert args.bandwidth_kbit is None or 128 <= args.bandwidth_kbit <= 1000000
name = args.name or ('dram-gpu-cooling-installed-checkpoint' if args.with_cooling else 'dram-gpu-installed-checkpoint')
assert not args.name or args.with_cooling
target = root/'build'/(name+'.tar.gz')
helper = [sys.executable, '-X', 'utf8', str(root/'tools/tablet_ssh.py')]
if args.verify_existing or args.download_existing:
    if args.verify_existing:
        assert target.is_file()
    output = (root/'evidence'/(name+'-capture.txt')).read_text(encoding='utf8')
else:
    assert not target.exists()
    subprocess.run(helper+['--file', str(root/'firmware/capture_dram_gpu_checkpoint.py'),
                          '--remote', '/home/debian/capture_dram_gpu_checkpoint.py'], check=True)
    command = 'python3 /home/debian/capture_dram_gpu_checkpoint.py'+(' --with-cooling' if args.with_cooling else '')
    if args.name:
        command += ' --name '+args.name
    result = subprocess.run(helper+['--root', '--command', command,
                    '--output', name+'-capture.txt', '--timeout', '150'],
                    check=True, capture_output=True, text=True, encoding='utf8')
    output = result.stdout
match = re.search(r'DRAM_GPU_INSTALLED_CHECKPOINT_CREATED (\{.*\})', output)
assert match, output
created = json.loads(match[1])
assert created['path'] == '/home/debian/'+name+'.tar.gz'
if not args.verify_existing:
    descriptor, temporary_name = tempfile.mkstemp(prefix=name+'-download-', dir=target.parent)
    import os
    os.close(descriptor)
    temporary = Path(temporary_name)
    limit = ['-l', str(args.bandwidth_kbit)] if args.bandwidth_kbit else []
    subprocess.run(['scp', *limit, '-i', str(root/'private/tzx-host-ed25519'), '-o', 'BatchMode=yes',
        '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile='+str(root/'private/tablet_known_hosts'),
        'debian@192.168.77.2:'+created['path'], str(temporary)], check=True, timeout=150)
    assert temporary.stat().st_size == created['bytes'] and hashlib.sha256(temporary.read_bytes()).hexdigest() == created['sha256']
    temporary.replace(target)
digest = hashlib.sha256(target.read_bytes()).hexdigest()
assert digest == created['sha256'] and target.stat().st_size == created['bytes']
with tarfile.open(target, 'r:gz') as archive:
    members = archive.getmembers()
    assert len({m.name for m in members}) == len(members)
    assert all(m.isfile() and not PurePosixPath(m.name).is_absolute() and '..' not in PurePosixPath(m.name).parts for m in members)
    manifest = json.load(archive.extractfile('MANIFEST.json'))
    assert manifest['cid'] == '3e01ff55454d20202010209170281b59'
    assert {m.name for m in members} == set(manifest['files']) | {'MANIFEST.json'}
    for member_name, expected in manifest['files'].items():
        assert hashlib.sha256(archive.extractfile(member_name).read()).hexdigest() == expected, member_name
record = dict(manifest, archive_sha256=digest, archive_bytes=target.stat().st_size,
              every_member_verified=True)
(root/'build'/(name+'.json')).write_text(json.dumps(record, indent=2)+'\n')
print('DRAM_GPU_INSTALLED_CHECKPOINT_RETRIEVED_EVERY_MEMBER_VERIFIED', json.dumps({
      'files': len(manifest['files']), 'bytes': record['archive_bytes'], 'sha256': digest}))
