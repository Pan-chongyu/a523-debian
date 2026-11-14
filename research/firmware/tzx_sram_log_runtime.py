"""Guard and archive a temporary SRAM recorder for the exact tested boot chain."""
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import time
import zlib

parser = argparse.ArgumentParser()
parser.add_argument('--live', action='store_true', help='Read current SRAM without loading a module')
args = parser.parse_args()
assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/class/block/mmcblk0/size').read_text().strip() == '244318208'
assert int(Path('/proc/sys/kernel/tainted').read_text()) in (0, 4096)
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
fd = os.open('/dev/mmcblk0', os.O_RDONLY)
try:
    toc0 = os.pread(fd, 40960, 256 * 512)
    assert hashlib.sha256(toc0).hexdigest() == 'ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df'
    header = bytearray(os.pread(fd, 512, 4096 * 512))
    assert header[:8] == b'A523BND1' and struct.unpack_from('<II', header, 8) == (1, 5)
    crc = struct.unpack_from('<I', header, 16)[0]
    struct.pack_into('<I', header, 16, 0)
    assert zlib.crc32(header) == crc
    lba, length, address, _, _, _ = struct.unpack_from('<6I', header, 32 + 4 * 24)
    assert (length, address) == (37028, 0x54000) and 4097 <= lba < 131072
    bl31 = os.pread(fd, length, lba * 512)
    assert hashlib.sha256(bl31).hexdigest() == '4f86a989584fe1e1312264ce549ecbb81bdc5656a2307cdef525371b81ad371a'
finally:
    os.close(fd)

module = Path(__file__).with_name('tzx_sram_log.ko')
if not args.live:
    assert not Path('/sys/module/tzx_sram_log').exists()
    assert hashlib.sha256(module.read_bytes()).hexdigest() == '4f0e595ed91fc68972f91d8757b73f814b11ff6f3fb9fbe3bcbaa9c691be891c'
    subprocess.run(['insmod', str(module), 'boot_id=' + boot], check=True, timeout=15)
    data = Path('/sys/kernel/tzx_sram_log/previous').read_bytes()
else:
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    try:
        with mmap.mmap(fd, 8192, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x5e000) as view:
            data = view[:]
    finally:
        os.close(fd)
assert len(data) == 8192
root = Path('/home/debian/tzx-reset-debug')
root.mkdir(mode=0o700, exist_ok=True)
stamp = ('live-' if args.live else 'previous-') + boot + '-' + str(time.time_ns())
report = {'boot_id': boot, 'source': 'live' if args.live else 'preserved_at_probe',
          'sram_base': '0x5e000', 'bytes': len(data),
          'raw_sha256': hashlib.sha256(data).hexdigest(), 'records': []}
for bank in range(2):
    chunk = data[bank * 4096:(bank + 1) * 4096]
    if chunk[:8] != b'TZXLOG1\0':
        report['records'].append({'bank': bank, 'valid_magic': False})
        continue
    version, reason, cpu, size, realtime, mono, crc, sequence = struct.unpack_from('<4I2Q2I', chunk, 8)
    assert version == 1 and size <= 3968
    log = chunk[128:128 + size]
    record = {'bank': bank, 'reason': reason, 'cpu': cpu, 'length': size,
              'time_unix': realtime / 1e9, 'monotonic_seconds': mono / 1e9,
              'crc_valid': zlib.crc32(log) == crc, 'sequence': sequence,
              'recorded_boot_id': chunk[48:88].split(b'\0', 1)[0].decode('ascii')}
    report['records'].append(record)
    (root / (stamp + '-bank' + str(bank) + '.txt')).write_bytes(log)
with (root / (stamp + '.bin')).open('xb') as stream:
    stream.write(data)
    stream.flush()
    os.fsync(stream.fileno())
(root / (stamp + '.json')).write_text(json.dumps(report, indent=2) + '\n')
print('SRAM_LOG_CAPTURE', str(root / stamp), json.dumps(report), flush=True)
