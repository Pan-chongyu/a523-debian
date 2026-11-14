"""Read-only search for hardware descriptions in the two eMMC boot areas.

Keep only summary counts and valid FDT hardware descriptions; never copy the
boot areas or print arbitrary contents, serial numbers, or stored credentials.
"""
import hashlib
import json
from pathlib import Path
import struct

assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
summary = []
for name in ('mmcblk0boot0', 'mmcblk0boot1'):
    length = int((Path('/sys/class/block') / name / 'size').read_text()) * 512
    assert 0 < length <= 16 * 1024 * 1024
    with open('/dev/' + name, 'rb', buffering=0) as source:
        data = source.read(length)
    assert len(data) == length
    fdt = []
    position = 0
    while True:
        position = data.find(b'\xd0\x0d\xfe\xed', position)
        if position < 0:
            break
        if position + 40 <= length:
            h = struct.unpack_from('>10I', data, position)
            _, size, off_struct, off_strings, off_reserve, version, last_version, _, strings_size, struct_size = h
            if (40 <= size <= length - position and version == 17 and last_version <= 17
                    and 40 <= off_struct < size and 40 <= off_strings < size
                    and off_struct + struct_size <= size and off_strings + strings_size <= size
                    and off_reserve + 16 <= size):
                payload = data[position:position + size]
                # Extract only hardware descriptions, after validating the header.
                target = Path('/home/debian') / (name + '-hardware-description.dtb')
                assert not target.exists()
                target.write_bytes(payload)
                fdt.append({'offset': position, 'size': size, 'file': str(target),
                            'sha256': hashlib.sha256(payload).hexdigest()})
        position += 4
    summary.append({'partition': name, 'bytes': length,
                    'sha256': hashlib.sha256(data).hexdigest(),
                    'zero_bytes': data.count(0), 'ff_bytes': data.count(255),
                    'valid_fdt': fdt})
print(json.dumps(summary, indent=2))
