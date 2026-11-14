"""Inspect a saved Panfrost v1 dump without exposing BO payloads."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

parser = argparse.ArgumentParser()
parser.add_argument('dump', type=Path)
args = parser.parse_args()
size = args.dump.stat().st_size
assert 0 < size <= 512 * 1024 * 1024
headers = []
registers = []
with args.dump.open('rb') as source:
    for index in range(4096):
        source.seek(index * 2000)
        header = source.read(2000)
        assert len(header) == 2000
        magic, kind, length, offset = struct.unpack_from('<4I', header)
        assert magic == 0x464e4150 and kind <= 3
        assert offset + length <= size
        item = {'type': kind, 'offset': offset, 'bytes': length}
        if kind == 0:
            jc, gpu, major, minor = struct.unpack_from('<QIII', header, 16)
            assert (major, minor) == (1, 0)
            item.update(job_chain=hex(jc), gpu_id=hex(gpu),
                        bo_count=struct.unpack_from('<Q', header, 40)[0])
            assert length % 8 == 0
            source.seek(offset)
            registers = [{'register': hex(reg), 'value': hex(value)}
                         for reg, value in struct.iter_unpack('<II', source.read(length))]
        elif kind == 1:
            assert length % 8 == 0
            source.seek(offset)
            pages = [p for (p,) in struct.iter_unpack('<Q', source.read(length)) if p]
            item.update(nonzero_physical_pages=len(pages),
                        physical_min=hex(min(pages)) if pages else None,
                        physical_max=hex(max(pages)) if pages else None,
                        pages_at_or_above_4gb=sum(p >= 1 << 32 for p in pages))
        elif kind == 2:
            item.update(valid=struct.unpack_from('<I', header, 16)[0],
                        iova=hex(struct.unpack_from('<Q', header, 24)[0]),
                        bomap_index=struct.unpack_from('<I', header, 32)[0])
        headers.append(item)
        if kind == 3:
            assert offset == size and length == 0
            break
    else:
        raise AssertionError('No trailer')
    source.seek(0)
    digest = hashlib.file_digest(source, 'sha256').hexdigest()
print(json.dumps({'path': str(args.dump), 'bytes': size, 'sha256': digest,
                  'headers': headers, 'registers': registers}, indent=2), flush=True)
