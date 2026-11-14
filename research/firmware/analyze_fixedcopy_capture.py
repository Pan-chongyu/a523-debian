"""Summarize a private diagnostic snapshot without reading any credentials."""
import collections
import hashlib
import json
from pathlib import Path
import re
import sys

prefix = sys.argv[1]
assert re.fullmatch(r'/home/debian/[a-zA-Z0-9_-]+', prefix)
expected = Path(prefix + '-expected.bin').read_bytes()
report = {'prefix': prefix, 'captures': {}}
for suffix in ('copied.bin', 'volatile-repeat.bin', 'expected.bin',
               'proc-source.bin', 'proc-target.bin'):
    path = Path(prefix + '-' + suffix)
    if not path.exists():
        continue
    data = path.read_bytes()
    assert len(data) == len(expected)
    bad = [i for i, (a, b) in enumerate(zip(data, expected)) if a != b]
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
                match = expected.find(block)
                record['cachelines'].append({'offset': hex(off), 'hex': block.hex(),
                    'matching_source_offset': hex(match) if match >= 0 else None})
    report['captures'][suffix] = record
print(json.dumps(report, indent=2), flush=True)
