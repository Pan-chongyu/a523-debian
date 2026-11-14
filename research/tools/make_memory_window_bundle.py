"""Limit only the DT memory extent for a reversible GPU address-range experiment."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib

root = Path(__file__).resolve().parents[1]
source = root / 'build/cpu-tlbi-kernel'
out = root / 'build/gpu-memory-window-3g'
manifest = json.loads((source / 'linux-bundle.json').read_text())
bundle = (source / 'linux-bundle.bin').read_bytes()
assert hashlib.sha256(bundle).hexdigest() == '32648d80d699892b3dcfe0be37fdc07a5ed30d95d8b9ad8cf2140bb6f3181799'
item = manifest['items'][1]
offset = (item['lba'] - 4096) * 512
dtb = bytearray(bundle[offset:offset + item['bytes']])
assert hashlib.sha256(dtb).hexdigest() == item['sha256']
magic, total, structure, strings = struct.unpack_from('>4I', dtb)
assert magic == 0xd00dfeed and total <= len(dtb)
cursor, stack, matches = structure, [], []
while True:
    token = struct.unpack_from('>I', dtb, cursor)[0]
    cursor += 4
    if token == 1:
        end = dtb.index(0, cursor)
        stack.append(dtb[cursor:end].decode())
        cursor = (end + 4) & ~3
    elif token == 2:
        stack.pop()
    elif token == 3:
        length, nameoff = struct.unpack_from('>II', dtb, cursor)
        cursor += 8
        end = dtb.index(0, strings + nameoff)
        name = dtb[strings + nameoff:end].decode()
        if '/'.join(stack) == '/memory@40000000' and name == 'reg':
            assert length == 16
            assert struct.unpack_from('>4I', dtb, cursor) == (0, 0x40000000, 1, 0)
            matches.append(cursor)
            struct.pack_into('>4I', dtb, cursor, 0, 0x40000000, 0, 0xc0000000)
        cursor = (cursor + length + 3) & ~3
    elif token == 4:
        continue
    elif token == 9:
        break
    else:
        raise ValueError(token)
assert len(matches) == 1 and not stack
raw = root / 'build/gpu-memory-window-3g.dtb'
raw.write_bytes(dtb)
subprocess.run([sys.executable, str(root / 'tools/make_same_slot_dtb.py'),
                str(source), str(raw), str(out)], check=True)
candidate = (out / 'linux-bundle.bin').read_bytes()
rounded = (item['bytes'] + 511) & ~511
assert bundle[512:offset] == candidate[512:offset]
assert bundle[offset + rounded:] == candidate[offset + rounded:]
before, after = bytearray(bundle[:512]), bytearray(candidate[:512])
for position in (16, 68):
    before[position:position+4] = after[position:position+4] = bytes(4)
assert before == after
changes = [i for i, (a,b) in enumerate(zip(bundle, candidate)) if a != b]
assert set(changes) <= set(range(16,20)) | set(range(68,72)) | set(range(offset + matches[0], offset + matches[0] + 16))
report = {'purpose': 'diagnostic_only_not_full_RAM_qualification',
          'physical_start': '0x40000000', 'physical_end_exclusive': '0x100000000',
          'advertised_RAM_GiB': 3, 'unchanged_kernel_and_modules': True,
          'original_bundle_sha256': hashlib.sha256(bundle).hexdigest(),
          'candidate_bundle_sha256': hashlib.sha256(candidate).hexdigest(),
          'changed_byte_offsets': changes,
          'write_ranges': [{'lba': 4096, 'sectors': 1}, {'lba': item['lba'], 'sectors': rounded // 512}],
          'dtb_reg_offset': matches[0], 'status': 'prepared_not_installed'}
(out / 'EXPERIMENT.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
