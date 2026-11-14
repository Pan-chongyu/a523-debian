"""Replace just a DTB while preserving every item placement and declared size."""
import argparse,hashlib,json,struct,zlib
from pathlib import Path
from fel_device import ROOT

p=argparse.ArgumentParser()
p.add_argument('source',type=Path)
p.add_argument('dtb',type=Path)
p.add_argument('output',type=Path)
a=p.parse_args()
source=(ROOT/a.source).resolve();out=(ROOT/a.output).resolve()
source.relative_to(ROOT);out.relative_to(ROOT)
assert source!=out
manifest=json.loads((source/'linux-bundle.json').read_text())
bundle=bytearray((source/'linux-bundle.bin').read_bytes())
assert hashlib.sha256(bundle).hexdigest()==manifest['sha256']
assert bundle[:8]==b'A523BND1'
dt=manifest['items'][1]
raw=a.dtb.read_bytes()
assert raw[:4]==bytes.fromhex('d00dfeed')
assert struct.unpack_from('>I',raw,4)[0]<=len(raw)<=dt['bytes']
data=raw+b'\0'*(dt['bytes']-len(raw))
rounded=data+b'\0'*(-len(data)%512)
offset=(dt['lba']-4096)*512
bundle[offset:offset+len(rounded)]=rounded
struct.pack_into('<I',bundle,68,zlib.crc32(rounded))
struct.pack_into('<I',bundle,16,0)
struct.pack_into('<I',bundle,16,zlib.crc32(bundle[:512]))
dt['sha256']=hashlib.sha256(data).hexdigest()
manifest.update(sha256=hashlib.sha256(bundle).hexdigest(),hardware_boot_verified=False,
                dtb_total_size=struct.unpack_from('>I',raw,4)[0],
                changed_ranges=[{'lba':4096,'sectors':1},
                                {'lba':dt['lba'],'sectors':len(rounded)//512}])
out.mkdir(parents=True,exist_ok=False)
(out/'linux-bundle.bin').write_bytes(bundle)
(out/'board.dtb').write_bytes(data)
(out/'linux-bundle.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
print(json.dumps(manifest,indent=2))
