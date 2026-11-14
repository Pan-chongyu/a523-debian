"""Preserve a known library cache mismatch before replacing it from verified disk bytes."""
import argparse
import ctypes
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import time

parser = argparse.ArgumentParser()
parser.add_argument('--repair', action='store_true')
parser.add_argument('--path', default='/usr/lib/aarch64-linux-gnu/libpcre2-8.so.0.14.0')
args = parser.parse_args()
assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
path = Path(args.path).resolve(strict=True)
assert str(path).startswith(('/usr/lib/', '/usr/bin/', '/usr/sbin/'))
size = path.stat().st_size
expected = None
for manifest in Path('/var/lib/dpkg/info').glob('*.md5sums'):
    for line in manifest.read_text().splitlines():
        digest, name = line.split(None, 1)
        if '/' + name == str(path):
            assert expected is None or expected == digest
            expected = digest
assert expected is not None, 'Missing package checksum'

fd = os.open(path, os.O_RDONLY | os.O_DIRECT)
try:
    with mmap.mmap(-1, (size + 4095) // 4096 * 4096) as buffer:
        assert os.readv(fd, [buffer]) == size
        disk = buffer[:size]
finally:
    os.close(fd)
assert hashlib.md5(disk).hexdigest() == expected, 'Disk bytes do not match package'
cached = path.read_bytes()
directory = Path('/home/debian/tzx-gpu-debug') / ('cache-' + str(int(time.time())))
directory.mkdir(mode=0o700, parents=True)
assert len(cached) == size
different = [offset for offset in range(0, size, 4096)
             if cached[offset:offset+4096] != disk[offset:offset+4096]]

fd = os.open(path, os.O_RDONLY)
with mmap.mmap(fd, size, flags=mmap.MAP_PRIVATE, prot=mmap.PROT_READ | mmap.PROT_WRITE) as mapping:
    address = ctypes.addressof(ctypes.c_char.from_buffer(mapping))
    pages = []
    with open('/proc/self/pagemap', 'rb', buffering=0) as pagemap:
        for offset in different:
            value = mapping[offset]  # fault the page without writing/COW
            pagemap.seek(((address + offset) // 4096) * 8)
            entry = struct.unpack('<Q', pagemap.read(8))[0]
            pfn = entry & ((1 << 55) - 1)
            row = {'file_offset': hex(offset), 'entry': hex(entry), 'pfn': hex(pfn),
                   'physical': hex(pfn * 4096), 'present': bool(entry & (1 << 63))}
            for name in ('kpageflags', 'kpagecount'):
                with open('/proc/' + name, 'rb', buffering=0) as stream:
                    stream.seek(pfn * 8)
                    row[name] = struct.unpack('<Q', stream.read(8))[0]
            bad = cached[offset:offset+4096]
            good = disk[offset:offset+4096]
            changed = [i for i, pair in enumerate(zip(bad, good)) if pair[0] != pair[1]]
            row.update(different_bytes=len(changed), first=changed[0], last=changed[-1],
                       bad_first_64=bad[:64].hex(), good_first_64=good[:64].hex(),
                       zero_bytes=bad.count(0))
            pages.append(row)
os.close(fd)
report = {'path': str(path), 'size': size, 'package_md5': expected,
          'cached_sha256': hashlib.sha256(cached).hexdigest(),
          'disk_sha256': hashlib.sha256(disk).hexdigest(), 'pages': pages}
for name, data in [('cached.bin', cached), ('direct.bin', disk)]:
    with (directory / name).open('wb') as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
(directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2), flush=True)
print('CAPTURE_DIRECTORY', directory, flush=True)
needle = cached[different[0]:different[0]+64] if different else b''
if different:
    # Match the changed cache line, rather than the unchanged start of its page.
    first_change = next(i for i, (a,b) in enumerate(zip(cached,disk)) if a != b)
    line_start = first_change & ~63
    needle = cached[line_start:line_start+64]
    matches = []
    for sentinel in Path('/home/debian').glob('gpu-*-sentinel.bin'):
        found = sentinel.read_bytes().find(needle)
        if found >= 0:
            matches.append({'file': str(sentinel), 'offset': found})
    report['matching_sentinels'] = matches
    (directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('SENTINEL_LINE_MATCHES', json.dumps(matches), flush=True)

if args.repair:
    assert different, 'No mismatch to repair'
    temporary = path.with_name(path.name + '.tzx-verified-disk')
    with temporary.open('xb') as output:
        output.write(disk)
        output.flush()
        os.fsync(output.fileno())
    temporary.chmod(0o644)
    assert hashlib.md5(temporary.read_bytes()).hexdigest() == expected
    temporary.replace(path)
    os.sync()
    assert hashlib.md5(path.read_bytes()).hexdigest() == expected
    print('LIBRARY_RESTORED_FROM_PACKAGE_VERIFIED_DIRECT_DISK_BYTES', str(path), flush=True)
