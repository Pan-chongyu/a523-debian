"""Switch the exact memory-extent DTB and header only; keep a checked full-RAM rollback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import zlib

parser = argparse.ArgumentParser()
parser.add_argument('--restore', action='store_true')
args = parser.parse_args()
assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#4 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/class/block/mmcblk0/size').read_text().strip() == '244318208'
assert not Path('/sys/module/panfrost').exists()
assert not Path('/var/lib/tzx/gpu-qualified').exists()
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
original_sha = '32648d80d699892b3dcfe0be37fdc07a5ed30d95d8b9ad8cf2140bb6f3181799'
size = 14809088
candidate_path = Path('/home/debian/gpu-memory-window-3g.bin')
experiment = json.loads(Path('/home/debian/gpu-memory-window-3g.json').read_text())
candidate = candidate_path.read_bytes()
assert experiment['original_bundle_sha256'] == original_sha
assert hashlib.sha256(candidate).hexdigest() == experiment['candidate_bundle_sha256']
assert len(candidate) == size
assert experiment['write_ranges'] == [{'lba':4096,'sectors':1},{'lba':28594,'sectors':42}]
backup = Path('/root/tzx-recovery/gpu-memory-window')
backup.mkdir(parents=True, exist_ok=True)
rollback = backup / 'full-4g-bundle.bin'
with open('/dev/mmcblk0', 'rb', buffering=0) as stream:
    stream.seek(4096 * 512)
    installed = stream.read(size)
if not args.restore:
    assert hashlib.sha256(installed).hexdigest() == original_sha
    if not rollback.exists():
        with rollback.open('xb') as stream:
            stream.write(installed)
            stream.flush()
            os.fsync(stream.fileno())
assert hashlib.sha256(rollback.read_bytes()).hexdigest() == original_sha
original = rollback.read_bytes()
expected_before = candidate if args.restore else original
target = original if args.restore else candidate
assert installed == expected_before

# Verify GPT identity without invoking shell parsing or changing the table.
with open('/dev/mmcblk0', 'rb', buffering=0) as stream:
    stream.seek(512)
    gpt = stream.read(512)
import uuid
assert gpt[:8] == b'EFI PART'
assert str(uuid.UUID(bytes_le=gpt[56:72])) == 'c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
dtb_offset = (28594 - 4096) * 512
assert original[512:dtb_offset] == candidate[512:dtb_offset]
assert original[dtb_offset+42*512:] == candidate[dtb_offset+42*512:]
for image in (original, candidate):
    header = bytearray(image[:512])
    crc = struct.unpack_from('<I', header, 16)[0]
    struct.pack_into('<I', header, 16, 0)
    assert zlib.crc32(header) == crc
    assert struct.unpack_from('<II', image, 56) == (28594, 21492)
    assert zlib.crc32(image[dtb_offset:dtb_offset+42*512]) == struct.unpack_from('<I', image, 68)[0]
assert original[:16] == candidate[:16]
header_a,header_b=bytearray(original[:512]),bytearray(candidate[:512])
for position in (16,68):
    header_a[position:position+4]=header_b[position:position+4]=bytes(4)
assert header_a == header_b

with open('/dev/mmcblk0', 'r+b', buffering=0) as stream:
    # Payload first, CRC header last. Every write stays inside the boot gap.
    for lba, sectors in ((28594,42),(4096,1)):
        offset = (lba - 4096) * 512
        data = target[offset:offset+sectors*512]
        assert lba >= 4096 and lba + sectors < 131072
        stream.seek(lba*512)
        assert stream.write(data) == len(data)
        os.fsync(stream.fileno())
        stream.seek(lba*512)
        assert stream.read(len(data)) == data
    stream.seek(4096*512)
    assert stream.read(size) == target
Path('/boot/board.dtb').write_bytes(target[dtb_offset:dtb_offset+21492])
os.sync()
print('MEMORY_WINDOW_FULL_READBACK_PASS', hashlib.sha256(target).hexdigest(), flush=True)
print('FULL_4G_RESTORED' if args.restore else 'THREE_GIB_DIAGNOSTIC_INSTALLED_WITH_FULL_4G_ROLLBACK', flush=True)
subprocess.run(['systemd-run', '--unit=tzx-memory-window-'+('restore' if args.restore else 'trial')+'-reboot',
                '--on-active=3s', '/usr/bin/systemctl', 'reboot'], check=True)
