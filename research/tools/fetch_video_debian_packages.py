"""Cache the exact signed-repository package requests on the faster host link."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import tarfile
import urllib.request

root=Path(__file__).resolve().parents[1];out=root/'downloads/video-debian';out.mkdir(exist_ok=True)
rows=re.findall(r"^'([^']+)' (\S+) (\d+) MD5Sum:([0-9a-f]{32})$",(root/'evidence/video-package-download-uris.txt').read_text(encoding='utf-8'),re.M)
assert rows
def fetch(row):
    url,name,size,md5=row;assert url.startswith('https://deb.debian.org/debian/') and Path(name).name==name
    path=out/name
    data=path.read_bytes() if path.exists() else urllib.request.urlopen(url,timeout=90).read()
    assert len(data)==int(size) and hashlib.md5(data).hexdigest()==md5,name
    path.write_bytes(data)
    return dict(url=url,file=name,bytes=len(data),apt_md5=md5,sha256=hashlib.sha256(data).hexdigest())
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool: records=list(pool.map(fetch,rows))
(out/'manifest.json').write_text(json.dumps(records,indent=2)+'\n')
with tarfile.open(root/'build/video/debian-packages.tar','w') as tf:
    for r in records:tf.add(out/r['file'],arcname=r['file'])
print('VERIFIED_EXACT_APT_REQUESTED_PACKAGES',len(records),sum(r['bytes'] for r in records))
