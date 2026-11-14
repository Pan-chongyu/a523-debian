"""Create the inactive HS kernel bundle from the verified extended bundle."""
import hashlib,json,struct,zlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
ext=json.loads((root/'build/extended-kernel/linux-bundle.json').read_text())
source=(root/'build/extended-kernel/linux-bundle.bin').read_bytes()
hs=(root/'build/hs-kernel/Image').read_bytes()
assert hashlib.sha256(source).hexdigest()==ext['sha256']
def payloads(bundle,start):
    out=[]
    for i in range(5):
        lba,length,address,crc,_,_=struct.unpack_from('<6I',bundle,32+i*24)
        off=(lba-start)*512;data=bundle[off:off+length]
        assert zlib.crc32(bundle[off:off+((length+511)//512*512)])==crc
        out.append((address,data))
    return out
parts=payloads(source,65536)
parts[0]=(parts[0][0],hs)
parts[3]=(parts[3][0],(root/'build/hs-kernel/linux-entry.bin').read_bytes())
header=bytearray(512);header[:8]=b'A523BND1';struct.pack_into('<II',header,8,1,5)
bundle=bytearray(512);items=[]
for i,(address,data) in enumerate(parts):
    padded=data+bytes((-len(data))%512);lba=98304+len(bundle)//512
    struct.pack_into('<6I',header,32+i*24,lba,len(data),address,zlib.crc32(padded),0,0)
    name=ext['items'][i]['file'];items.append(dict(file=name,lba=lba,bytes=len(data),load_address=f'0x{address:08x}',sha256=hashlib.sha256(data).hexdigest()))
    bundle.extend(padded)
struct.pack_into('<I',header,16,zlib.crc32(header));bundle[:512]=header
assert 98304+len(bundle)//512<131072
out=root/'build/hs-kernel';(out/'linux-bundle.bin').write_bytes(bundle)
manifest=dict(start_lba=98304,header_lba=4096,bytes=len(bundle),sectors=len(bundle)//512,
    sha256=hashlib.sha256(bundle).hexdigest(),header_sha256=hashlib.sha256(header).hexdigest(),
    previous_bundle_sha256=ext['sha256'],previous_start_lba=65536,
    config_sha256=hashlib.sha256((out/'kernel.config').read_bytes()).hexdigest(),
    config_change='HS200/HS400 exact-CID opt-in driver; normal boot remains DDR52',items=items,
    hardware_boot_verified=False)
(out/'linux-bundle.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({k:manifest[k] for k in ('bytes','sha256','header_sha256','config_sha256')},indent=2))
