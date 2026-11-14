"""Retain the installed DRAM/DTB/initramfs/BL31; replace kernel and entry only."""
import hashlib,json,struct,zlib
from pathlib import Path
r=Path(__file__).resolve().parents[1]
out=r/'build/cpu-gpu-kernel'
old=json.loads((r/'build/hs-kernel/linux-bundle.json').read_text())
source=(r/'build/hs-kernel/linux-bundle.bin').read_bytes()
assert hashlib.sha256(source).hexdigest()==old['sha256']=='2792b0e8b1087287c4e1da8f036fb3a72b11d4b5e21da7e38111d90785a6509e'
parts=[]
for i in range(5):
    lba,n,address,crc,_,_=struct.unpack_from('<6I',source,32+i*24)
    off=(lba-old['start_lba'])*512;padded=source[off:off+((n+511)&~511)]
    assert zlib.crc32(padded)==crc
    parts.append((address,padded[:n]))
parts[0]=(parts[0][0],(out/'Image').read_bytes())
parts[3]=(parts[3][0],(out/'linux-entry.bin').read_bytes())
header=bytearray(512);header[:8]=b'A523BND1';struct.pack_into('<II',header,8,1,5)
bundle=bytearray(512);items=[]
for i,(address,data) in enumerate(parts):
    padded=data+bytes((-len(data))%512);lba=98304+len(bundle)//512
    struct.pack_into('<6I',header,32+i*24,lba,len(data),address,zlib.crc32(padded),0,0)
    items.append(dict(file=old['items'][i]['file'],lba=lba,bytes=len(data),load_address=f'0x{address:08x}',sha256=hashlib.sha256(data).hexdigest()))
    bundle.extend(padded)
struct.pack_into('<I',header,16,zlib.crc32(header));bundle[:512]=header
assert 98304+len(bundle)//512<131072
config=(out/'kernel.config').read_bytes()
before=(r/'build/hs-kernel/kernel.config').read_text().splitlines();after=config.decode().splitlines()
assert set(after)-set(before)=={'CONFIG_SCHED_MC=y','CONFIG_DEVFREQ_THERMAL=y'}
assert set(before)-set(after)=={'# CONFIG_SCHED_MC is not set','# CONFIG_DEVFREQ_THERMAL is not set'}
manifest=dict(start_lba=98304,header_lba=4096,bytes=len(bundle),sha256=hashlib.sha256(bundle).hexdigest(),
    header_sha256=hashlib.sha256(header).hexdigest(),config_sha256=hashlib.sha256(config).hexdigest(),
    panfrost_sha256=hashlib.sha256((out/'panfrost.ko').read_bytes()).hexdigest(),items=items,
    previous_bundle_sha256=old['sha256'],preserved_fallback_lba=65536,
    config_changes=['SCHED_MC','DEVFREQ_THERMAL'],source_changes=['queued arch topology refresh for the board DVFS replacement'],
    gpu_source='byte-identical qualified DMA32/MMU-init/AARCH64 sources; rebuilt for native devfreq cooling')
(out/'linux-bundle.bin').write_bytes(bundle)
(out/'linux-bundle.json').write_text(json.dumps(manifest,indent=2)+'\n',newline='\n')
print(json.dumps({k:v for k,v in manifest.items() if k!='items'},indent=2))
