"""Recover small error captures from exact cache-line deltas and a pinned file."""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('analysis', type=Path)
parser.add_argument('expected', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
report = json.loads(args.analysis.read_text(encoding='utf8'))
expected = args.expected.read_bytes()
if 'trusted_reference_sha256' in report:
    assert hashlib.sha256(expected).hexdigest() == report['trusted_reference_sha256']
else:
    assert hashlib.sha256(expected).hexdigest() == report['captures']['expected.bin']['sha256']
    assert report['captures']['expected.bin']['changed_bytes'] == 0
args.output.mkdir(parents=True, exist_ok=True)
recovered = {}
for name, record in report['captures'].items():
    assert '/' not in name and '\\' not in name
    data = bytearray(expected)
    if record['changed_bytes']:
        assert record.get('cachelines'), 'delta range too large to reconstruct'
        for line in record['cachelines']:
            start = int(line['offset'], 16)
            block = bytes.fromhex(line['hex'])
            assert len(block) == 64 and 0 <= start <= len(data)-64
            data[start:start+64] = block
    assert len(data) == record['bytes']
    assert hashlib.sha256(data).hexdigest() == record['sha256'], name
    path = args.output/name
    assert not path.exists() or path.read_bytes() == data
    path.write_bytes(data)
    recovered[name] = record['sha256']
(args.output/'MANIFEST.json').write_text(json.dumps({'source': str(args.analysis.resolve()),
    'method': 'exact cacheline deltas, entire reconstructed file SHA256 checked',
    'files': recovered}, indent=2)+'\n', encoding='utf8')
print('EXACT_CAPTURE_RECONSTRUCTION_PASS', len(recovered), args.output)
