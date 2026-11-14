"""Reserve the splash's physical pages without moving any existing payload."""
import hashlib,json,struct,subprocess,zlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'build/boot-logo'
base=root/'build/cpu-gpu-kernel';old=(base/'linux-bundle.bin').read_bytes()
m=json.loads((base/'linux-bundle.json').read_text())
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(old)==m['sha256']=='c5d306559886e947d702457a92149e4c2e6c41713188bee6bbbdcc22409f0da7'
item=m['items'][1];offset=(item['lba']-m['start_lba'])*512
dtb=old[offset:offset+item['bytes']];assert sha(dtb)==item['sha256']
path=out/'board.dtb';path.write_bytes(dtb)
wsl='/mnt/c/Users/pan75/Documents/ChatGPT/A523适配debian/build/boot-logo/board.dtb'
for args in (['-c',wsl,'/reserved-memory/boot-splash@42000000'],
             ['-t','x',wsl,'/reserved-memory/boot-splash@42000000','reg','0','42000000','0','900000'],
             [wsl,'/reserved-memory/boot-splash@42000000','no-map']):
    subprocess.run(['wsl','-d','Ubuntu-22.04','--','fdtput',*args],check=True)
candidate=path.read_bytes();rounded=(item['bytes']+511)&~511
assert len(candidate)<=rounded,(len(candidate),rounded)
new=bytearray(old);new[offset:offset+rounded]=candidate+bytes(rounded-len(candidate))
struct.pack_into('<II',new,32+24+4,len(candidate),int(item['load_address'],16))
struct.pack_into('<I',new,32+24+12,zlib.crc32(new[offset:offset+rounded]))
struct.pack_into('<I',new,16,0);struct.pack_into('<I',new,16,zlib.crc32(new[:512]))
assert new[512:offset]==old[512:offset] and new[offset+rounded:]==old[offset+rounded:]
manifest=json.loads(json.dumps(m));manifest.update(previous_bundle_sha256=sha(old),sha256=sha(new),
    header_sha256=sha(new[:512]),changed_payloads=['board.dtb'],reserved_boot_splash=[0x42000000,0x900000])
manifest['items'][1].update(bytes=len(candidate),sha256=sha(candidate))
(out/'linux-bundle.bin').write_bytes(new);(out/'linux-bundle.json').write_text(json.dumps(manifest,indent=2)+'\n')
(out/'active-header.bin').write_bytes(new[:512]);(out/'dtb-sectors.bin').write_bytes(new[offset:offset+rounded])
print('BOOT_LOGO_RESERVED_MEMORY_DTB_BUILT',len(candidate),sha(new),flush=True)
