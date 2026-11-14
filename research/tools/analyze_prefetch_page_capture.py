"""Check the frozen libc capture against its independently pinned disk reference."""
import hashlib
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
archive_path = root/'build/gpu-bl31-prefetch-context-cache-capture.tar.gz'
trusted = '70fa4c4cf57eabeb96097cce47582d02379c4cd1de3db3e98ade4dd7089a1b13'
with tarfile.open(archive_path) as archive:
    content = {m.name:archive.extractfile(m).read() for m in archive.getmembers()}
manifest = json.loads(content['MANIFEST.json'])
for name, digest in manifest['files'].items():
    assert hashlib.sha256(content[name]).hexdigest() == digest, name
expected = content['expected.bin']
assert hashlib.sha256(expected).hexdigest() == trusted
assert content['direct-after.bin'] == expected
changed = json.loads(content['changed.json'])
views = json.loads(content['independent-views.json'])
records = {}
for name in ('changed-cache.bin','expected.bin','direct-after.bin',
             'page-cf000-proc-copy.bin','page-cf000-proc-mapping.bin',
             'page-cf000-repeat-mapping.bin'):
    data = content[name]
    offset = 0xcf000 if name.startswith('page-') else 0
    reference = expected[offset:offset+len(data)]
    assert len(data) == len(reference)
    bad = [n for n,(a,b) in enumerate(zip(data,reference)) if a != b]
    row = {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'changed_bytes':len(bad)}
    if bad:
        row.update(first_file_offset=hex(offset+bad[0]),last_file_offset=hex(offset+bad[-1]))
        row['cachelines'] = []
        for start in sorted({n//64*64 for n in bad}):
            block = data[start:start+64]
            source_offset = expected.find(block)
            row['cachelines'].append({'file_offset':hex(offset+start),'hex':block.hex(),
                'matching_reference_offset':hex(source_offset) if source_offset >= 0 else None})
    records[name] = row
report = {'archive_sha256':hashlib.sha256(archive_path.read_bytes()).hexdigest(),
    'pinned_trusted_libc_sha256':trusted,'captured':changed,'independent_views':views,
    'changed_copy_line_physical_address_known':False,
    'physical_address_limit':'Recorded copy PFN is for logical page start at VA 0x3ed3f60; bad line VA 0x3ed4d20 crosses that page. Its PFN was not saved.',
    'files':records,'interpretation':'Original mapping and direct disk correct; copied buffer independently wrong. No writer attributed.'}
out = root/'evidence/bl31-prefetch-context-host-analysis.json'
out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report,indent=2))
