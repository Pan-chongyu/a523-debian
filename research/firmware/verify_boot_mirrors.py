"""Verify the installed raw boot image, then refresh its /boot file copies.

Only /boot mirrors are written. The raw eMMC boot area and partitions stay
untouched. Run on the tablet with the matching installed-bundle.json.
"""
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import zlib

assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/class/block/mmcblk0/size').read_text().strip() == '244318208'
assert subprocess.check_output(['blkid', '-s', 'PTUUID', '-o', 'value', '/dev/mmcblk0'], text=True).strip() == 'c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
manifest = json.loads(Path('/home/debian/installed-bundle.json').read_text())
assert manifest['start_lba'] == 4096
assert manifest['bytes'] == manifest['sectors'] * 512
assert (4096 + manifest['sectors']) < 131072
with open('/dev/mmcblk0', 'rb', buffering=0) as disk:
    disk.seek(256 * 512)
    loader = disk.read(40960)
    assert hashlib.sha256(loader).hexdigest() == 'ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df'
    disk.seek(4096 * 512)
    bundle = disk.read(manifest['bytes'])
assert hashlib.sha256(bundle).hexdigest() == manifest['sha256']
assert bundle[:8] == b'A523BND1' and struct.unpack_from('<II', bundle, 8) == (1, 5)
header = bytearray(bundle[:512])
expected_crc = struct.unpack_from('<I', header, 16)[0]
struct.pack_into('<I', header, 16, 0)
assert zlib.crc32(header) == expected_crc
assert len(manifest['items']) == 5
copies = {}
for index, item in enumerate(manifest['items']):
    lba, size, address, crc, _, _ = struct.unpack_from('<6I', bundle, 32 + 24 * index)
    assert (lba, size, address) == (item['lba'], item['bytes'], int(item['load_address'], 16))
    offset = (lba - 4096) * 512
    rounded = (size + 511) & ~511
    assert 512 <= offset and offset + rounded <= len(bundle)
    assert zlib.crc32(bundle[offset:offset + rounded]) == crc
    payload = bundle[offset:offset + size]
    assert hashlib.sha256(payload).hexdigest() == item['sha256']
    if item['file'] in ('Image', 'board.dtb', 'initramfs.cpio.gz'):
        copies[item['file']] = payload
assert set(copies) == {'Image', 'board.dtb', 'initramfs.cpio.gz'}
assert subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '--target', '/boot'], text=True).strip() == '/dev/mmcblk0p1'
copies['kernel.config'] = gzip.decompress(Path('/proc/config.gz').read_bytes())
for name, payload in copies.items():
    temporary = Path('/boot', name + '.verified-new')
    with temporary.open('wb') as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, Path('/boot', name))
    assert Path('/boot', name).read_bytes() == payload
    print('BOOT_MIRROR_VERIFIED', name, len(payload), hashlib.sha256(payload).hexdigest())
os.sync()
print('INSTALLED_BUNDLE_VERIFIED', manifest['sha256'])
print('INSTALLED_ORIGINAL_LOADER_VERIFIED', hashlib.sha256(loader).hexdigest())
print('BOOT_ID', Path('/proc/sys/kernel/random/boot_id').read_text().strip())
print(subprocess.check_output(['uname', '-a'], text=True).strip())
