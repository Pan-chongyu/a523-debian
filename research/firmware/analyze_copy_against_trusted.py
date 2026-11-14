"""Compare every captured buffer, including the reference, to a pinned file."""
import collections
import hashlib
import json
from pathlib import Path
import re
import sys

prefix = sys.argv[1]
assert re.fullmatch(r'/home/debian/[a-zA-Z0-9_-]+', prefix)
trusted_sha = '9d86f5b4be765956f050fc52a948c2c3fd47064a495f6bcdd44738c726bc6a77'
library = Path('/usr/lib/aarch64-linux-gnu/libgio-2.0.so.0.8400.4')
reference = library.read_bytes()
assert len(reference) == 2231760
assert hashlib.sha256(reference).hexdigest() == trusted_sha
report = {'prefix': prefix, 'trusted_reference_sha256': trusted_sha,
          'anchor': str(library), 'captures': {}}
for suffix in ('copied.bin', 'volatile-repeat.bin', 'expected.bin',
               'proc-source.bin', 'proc-target.bin'):
    data = Path(prefix + '-' + suffix).read_bytes()
    assert len(data) == len(reference)
    bad = [i for i, (a, b) in enumerate(zip(data, reference)) if a != b]
    record = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
              'changed_bytes': len(bad)}
    if bad:
        low, high = bad[0]//64*64, (bad[-1]//64+1)*64
        record.update(first=hex(bad[0]), last=hex(bad[-1]),
                      value_counts=dict(collections.Counter(data[low:high])))
        if high-low <= 4096:
            record['cachelines'] = []
            for off in range(low, high, 64):
                block = data[off:off+64]
                match = reference.find(block)
                record['cachelines'].append({'offset': hex(off), 'hex': block.hex(),
                    'matching_source_offset': hex(match) if match >= 0 else None})
    report['captures'][suffix] = record
print(json.dumps(report, indent=2), flush=True)
