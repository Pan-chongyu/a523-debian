"""Check warm-reset retention of GP1..3 for the immutable installed loader.

The installed eMMC init overwrites GP0, while GP4..7 are boot diagnostics.
Neither bank, the FEL-request marker, nor RTC clock/alarm registers are written.
"""
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import secrets
import struct
import time

parser = argparse.ArgumentParser()
parser.add_argument('action', choices=('arm', 'check', 'read'))
args = parser.parse_args()
assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
fd = os.open('/dev/mmcblk0', os.O_RDONLY)
try:
    assert hashlib.sha256(os.pread(fd, 40960, 256 * 512)).hexdigest() == 'ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df'
finally:
    os.close(fd)
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
root = Path('/home/debian/tzx-reset-debug')
root.mkdir(mode=0o700, exist_ok=True)
state = root / 'rtc-retention-test.json'
fd = os.open('/dev/mem', (os.O_RDONLY if args.action == 'read' else os.O_RDWR) | os.O_SYNC)
try:
    with mmap.mmap(fd, 4096, mmap.MAP_SHARED,
                   mmap.PROT_READ | (0 if args.action == 'read' else mmap.PROT_WRITE),
                   offset=0x07090000) as view:
        before = struct.unpack_from('<8I', view, 0x100)
        result = {'time_unix': time.time(), 'boot_id': boot, 'action': args.action,
                  'gp_before': [hex(v) for v in before], 'write_offsets': []}
        if args.action == 'arm':
            assert not state.exists(), 'Do not overwrite an unfinished retention test'
            markers = [0x54585A31, secrets.randbits(32), secrets.randbits(32)]
            saved = {'boot_id': boot, 'previous': list(before[1:4]), 'markers': markers}
            with state.open('x', encoding='ascii') as stream:
                json.dump(saved, stream)
                stream.flush()
                os.fsync(stream.fileno())
            for index, value in enumerate(markers):
                struct.pack_into('<I', view, 0x104 + index * 4, value)
            assert list(struct.unpack_from('<3I', view, 0x104)) == markers
            result.update(markers=[hex(v) for v in markers], write_offsets=['0x104', '0x108', '0x10c'])
        elif args.action == 'check':
            saved = json.loads(state.read_text())
            assert boot != saved['boot_id'], 'Check requires a different boot ID'
            result.update(recorded_boot_id=saved['boot_id'],
                          retained=list(before[1:4]) == saved['markers'],
                          markers=[hex(v) for v in saved['markers']])
            for index, value in enumerate(saved['previous']):
                struct.pack_into('<I', view, 0x104 + index * 4, value)
            assert list(struct.unpack_from('<3I', view, 0x104)) == saved['previous']
            result.update(restored=True, write_offsets=['0x104', '0x108', '0x10c'])
            state.rename(root / ('rtc-retention-tested-' + boot + '.json'))
        result['gp_after'] = [hex(v) for v in struct.unpack_from('<8I', view, 0x100)]
finally:
    os.close(fd)
print(json.dumps(result, indent=2), flush=True)
if args.action == 'check':
    assert result['retained'], 'RTC GP1..3 did not retain the test markers'
