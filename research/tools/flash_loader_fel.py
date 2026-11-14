"""Write one new project TOC0 into its GPT boot gap, preserving partitions."""
import argparse,hashlib,json
from flash_linux_probe import ProbeWriter
from fel_device import ROOT,parse_gpt

p=argparse.ArgumentParser();p.add_argument('toc0');a=p.parse_args()
path=(ROOT/a.toc0).resolve();path.relative_to(ROOT.resolve())
data=path.read_bytes();m=json.loads(path.with_suffix(path.suffix+'.json').read_text())
assert data[:8]==b'TOC0.GLH' and 0<len(data)<=65536 and len(data)%512==0
assert hashlib.sha256(data).hexdigest()==m['image_sha256'] and len(data)==m['image_bytes']
d=ProbeWriter(0)
try:
    d.connect();identity=d.verify_identity()
    gpt=parse_gpt(d.read(0,128))
    assert gpt['disk_uuid']=='c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
    assert min(x['start'] for x in gpt['partitions'])>=131072
    d.write_verified(256,data)
    d._write_raw(0x07090110,b'\0'*16)
    report={'sha256':m['image_sha256'],'lba':256,'bytes':len(data),
            'readback':'PASS','cid':identity['cid'],'gpt_preserved':gpt}
    (ROOT/'evidence/loader-fel-update.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))
finally:d.close()
