"""Freeze selected reference files at the previously recorded Git commit."""
import hashlib
import json
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parents[1] / 'upstream/performance-reference'
tree = json.loads((root/'TREE.json').read_text())
entries = tree.get('tree', tree) if isinstance(tree, dict) else tree
prefixes = ('0013-', '0015-', '0016-', '0017-', '0025-', '0033-',
            '0035-', '0036-', '0051-', '0055-', '0067-', '0080-',
            '0103-', '0112-', '0136-')
records = []
for entry in entries:
    name = Path(entry['path']).name
    if not name.startswith(prefixes) or entry['type'] != 'blob':
        continue
    url = 'https://raw.githubusercontent.com/ut-slayer/orangepi-4a-mainline/38eb27cff2181ca784bca1030b83e41d8ec789e1/' + entry['path']
    target = root/name
    data = target.read_bytes() if target.exists() else urllib.request.urlopen(url, timeout=45).read()
    assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest() == entry['sha'], name
    target.write_bytes(data)
    records.append(dict(file=name, url=url, git_blob=entry['sha'],
                        sha256=hashlib.sha256(data).hexdigest(), applied=False))
(root/'EXTENDED-SOURCES.json').write_text(json.dumps(records, indent=2)+'\n')
print('VERIFIED_REFERENCE_FILES', len(records))
