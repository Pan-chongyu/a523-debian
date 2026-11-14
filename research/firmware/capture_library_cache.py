"""Preserve mismatched library cache pages; repair only a package-verified disk copy."""
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
parser.add_argument('path', type=Path)
parser.add_argument('--repair', action='store_true')
args = parser.parse_args()
assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
path = args.path.resolve(strict=True)
assert path.parent == Path('/usr/lib/aarch64-linux-gnu') and path.name.startswith('lib')
original = path.stat()
cached = path.read_bytes()
direct_copies = []
for attempt in range(2):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECT)
    try:
        with mmap.mmap(-1, (original.st_size + 4095) // 4096 * 4096) as buffer:
            total = 0
            while total < original.st_size:
                assert total % 512 == 0
                view = memoryview(buffer)[total:]
                try:
                    count = os.readv(fd, [view])
                finally:
                    view.release()
                assert count > 0
                total += count
            assert total == original.st_size
            direct_copies.append(buffer[:original.st_size])
    finally:
        os.close(fd)
assert direct_copies[0] == direct_copies[1], 'Independent disk reads differ'
direct = direct_copies[0]
expected = set()
for record in Path('/var/lib/dpkg/info').glob('*.md5sums'):
    for line in record.read_text().splitlines():
        digest, sep, name = line.partition('  ')
        if sep and name == str(path).lstrip('/'):
            expected.add(digest)
assert expected == {hashlib.md5(direct).hexdigest()}, ('Disk package verification failed', expected)
pages = []
with path.open('r+b', buffering=0) as stream:
    with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_COPY) as mapping:
        address = ctypes.addressof(ctypes.c_char.from_buffer(mapping))
        with open('/proc/self/pagemap', 'rb', buffering=0) as pagemap:
            for offset in range(0, len(cached), 4096):
                if cached[offset:offset+4096] == direct[offset:offset+4096]:
                    continue
                # Fault the original file-backed page in, without writing it.
                value = mapping[offset]
                pagemap.seek(((address + offset) // 4096) * 8)
                entry = struct.unpack('<Q', pagemap.read(8))[0]
                changed = [i for i, pair in enumerate(zip(cached[offset:offset+4096],
                                                         direct[offset:offset+4096]))
                           if pair[0] != pair[1]]
                pages.append({'offset': offset, 'physical_page': hex((entry & ((1 << 55)-1))*4096),
                              'pagemap_entry': hex(entry), 'changed_bytes': len(changed),
                              'first_changed': offset + min(changed),
                              'last_changed': offset + max(changed)})
directory = Path('/home/debian/tzx-gpu-debug/library-' + str(time.time_ns()))
directory.mkdir(mode=0o700, parents=True)
(directory / 'cached.bin').write_bytes(cached)
(directory / 'direct.bin').write_bytes(direct)
report = {'path': str(path), 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'cached_sha256': hashlib.sha256(cached).hexdigest(),
          'direct_sha256': hashlib.sha256(direct).hexdigest(), 'package_md5': sorted(expected),
          'size': len(cached), 'pages': pages, 'repair_requested': args.repair}
(directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
os.sync()
if args.repair and cached != direct:
    replacement = path.with_name(path.name + '.tzx-verified-disk')
    with replacement.open('xb') as output:
        output.write(direct)
        output.flush()
        os.fsync(output.fileno())
    os.chown(replacement, original.st_uid, original.st_gid)
    replacement.chmod(original.st_mode & 0o7777)
    assert replacement.read_bytes() == direct
    replacement.replace(path)
    os.sync()
    assert path.read_bytes() == direct
    print('VERIFIED_DISK_NEW_INODE_REPAIR_PASS', str(path), flush=True)
print('LIBRARY_CACHE_CAPTURE', str(directory), json.dumps(report), flush=True)
