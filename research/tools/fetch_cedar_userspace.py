"""Fetch the A523/T527 vendor codec package from its published SDK repository."""
import hashlib
import json
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parents[1]
tree = json.loads((root/'upstream/performance-reference/radxa-debian-tree.json').read_text())
output = root/'downloads/cedar-userspace'
output.mkdir(parents=True, exist_ok=True)
names = {'libcedarc-dev_1.0.0_arm64.deb',
         'gstreamer1.0-omx-allwinner-config_1.18.3-1.1_arm64.deb',
         'gstreamer1.0-omx-allwinner_1.18.3-1.1_arm64.deb'}
records=[]
for entry in tree['tree']:
    name=Path(entry['path']).name
    if name not in names:
        continue
    url='https://raw.githubusercontent.com/radxa/allwinner-debian/'+tree['sha']+'/'+entry['path']
    destination=output/name
    data=destination.read_bytes() if destination.exists() else urllib.request.urlopen(url,timeout=60).read()
    assert len(data)==entry['size']
    assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==entry['sha']
    destination.write_bytes(data)
    records.append(dict(file=name,url=url,git_blob=entry['sha'],sha256=hashlib.sha256(data).hexdigest()))
assert len(records)==3
(output/'SOURCES.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps(records,indent=2))
