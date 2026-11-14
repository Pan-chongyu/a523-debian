"""Check CPU RAM and disk/page-cache agreement without using the GPU."""
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import subprocess
import time
from tzx_direct_io import read_direct

parser = argparse.ArgumentParser()
parser.add_argument('--files-only', action='store_true')
args = parser.parse_args()
assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
if not args.files_only:
    assert not Path('/sys/module/panfrost').exists(), 'GPU must remain disabled for this baseline'
binary = Path('/home/debian/memory-check')
expected_binary = 'f2d244daddb707a9454a4dfa2fed15ab37917c409cc1012326c0d8aa23c2ea5d'
assert hashlib.sha256(binary.read_bytes()).hexdigest() == expected_binary
binary.chmod(0o755)
files = {Path('/usr/lib/aarch64-linux-gnu/libmount.so.1.1.0')}
for path in [Path('/usr/bin/glmark2-es2-drm'), Path('/usr/bin/glmark2-es2'),
             Path('/usr/lib/aarch64-linux-gnu/dri/panfrost_dri.so')]:
    if path.is_file(): files.add(path.resolve())
files.update(Path('/usr/lib/aarch64-linux-gnu').glob('libgallium-*.so'))
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        for row in (proc/'maps').read_text().splitlines():
            fields = row.split(None, 5)
            if len(fields) == 6 and fields[-1].startswith(('/usr/lib/', '/lib/', '/usr/bin/', '/usr/sbin/')):
                p = Path(fields[-1])
                if p.is_file():
                    files.add(p.resolve())
    except (OSError, ProcessLookupError):
        pass
expected = {}
for path in Path('/var/lib/dpkg/info').glob('*.md5sums'):
    for row in path.read_text(errors='replace').splitlines():
        digest, sep, name = row.partition('  ')
        if sep:
            expected['/'+name] = digest

def check_files(phase):
    total = 0
    for p in sorted(files):
        data = p.read_bytes()
        if not data:
            continue
        direct_hash = hashlib.sha256(read_direct(p)).hexdigest()
        assert hashlib.sha256(data).hexdigest() == direct_hash, ('CACHE_MISMATCH', str(p))
        digest = expected.get(str(p))
        if digest:
            assert hashlib.md5(data).hexdigest() == digest, ('PACKAGE_MISMATCH', str(p))
        total += len(data)
    print(json.dumps({'phase': phase, 'files': len(files), 'bytes': total, 'cache_disk_and_available_package_hashes': 'PASS'}), flush=True)

check_files('before')
if args.files_only:
    print('MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS', flush=True)
    raise SystemExit(0)
zones = list(Path('/sys/class/thermal').glob('thermal_zone*'))
assert len(zones) == 5
peaks = {}
for cycle in range(3):
    started = time.monotonic()
    process = subprocess.Popen([str(binary)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        while process.poll() is None:
            for p in zones:
                kind = (p/'type').read_text().strip()
                value = int((p/'temp').read_text())
                peaks[kind] = max(peaks.get(kind, value), value)
                assert 0 < value < 75000, ('TEMPERATURE_GUARD', kind, value)
            assert time.monotonic()-started < 45, 'RAM test deadline'
            time.sleep(0.5)
        print(process.communicate()[0], end='', flush=True)
        assert process.returncode == 0, process.returncode
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    check_files('after-cycle-'+str(cycle+1))
assert not int(Path('/proc/sys/kernel/tainted').read_text()) & 128
print('SOFTWARE_DESKTOP_MEMORY_BASELINE_PASS', json.dumps(peaks), flush=True)
