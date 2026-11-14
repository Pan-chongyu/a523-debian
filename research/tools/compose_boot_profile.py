"""Add counters to the exact early-CPUB image, retaining its executable bytes."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from make_toc0 import build

root=Path(__file__).resolve().parents[1]
folder=root/'build/boot-profile'
folder.mkdir(exist_ok=True)
assert not (folder/'loader.toc0').exists()
subprocess.run(['wsl','-d','Ubuntu-22.04','--','sh',
    '/mnt/c/Users/pan75/Documents/ChatGPT/A523适配debian/tools/build_boot_profile.sh'],check=True)
base=root/'build/boot-early-cpub'
old=(base/'loader.bin').read_bytes()
previous=json.loads((base/'loader.toc0.json').read_text())
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha((base/'loader.toc0').read_bytes())==previous['image_sha256']=='70efff1506d33cd90931197b5b558cace64720dca5e4b7a3d6db688851526db0'
assert sha(old)==previous['loader_sha256'] and len(old)==33816
symbols={p[2]:int(p[0],16) for s in (folder/'profile-hook.symbols.txt').read_text().splitlines()
    if len(p:=s.split())==3 and p[1] in ('T','t')}
hook=(folder/'profile-hook.bin').read_bytes()
assert symbols['boot_profile_init']==0x4c500 and len(hook)<=2048
new=bytearray(old)
patches=[]
for address,was,symbol,link in (
    (0x444a0,0xeb001f96,'boot_profile_init',True),
    (0x44cf0,0xeaffffad,'boot_profile_read',False),
    (0x44454,0xea001e69,'boot_profile_crc',False)):
    offset=address-0x44000
    assert struct.unpack_from('<I',old,offset)[0]==was,hex(address)
    entry=symbols[symbol]
    value=(0xeb000000 if link else 0xea000000)|(((entry-address-8)//4)&0xffffff)
    struct.pack_into('<I',new,offset,value)
    patches.append(dict(address=address,old=was,new=value,entry=entry,symbol=symbol))
allowed={i for item in patches for i in range(item['address']-0x44000,item['address']-0x44000+4)}
assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(new,old)))
new+=bytes(0x4c500-0x44000-len(new))+hook
assert len(new)+0xf80<=40960
(folder/'loader.bin').write_bytes(new)
build(bytes(new),0x44000,folder/'loader.toc0')
manifest=json.loads((folder/'loader.toc0.json').read_text())
manifest.update(previous_toc0_sha256=previous['image_sha256'],previous_loader_sha256=sha(old),
    loader_sha256=sha(new),patches=patches,hook_entry='0x4c500',hook_bytes=len(hook),
    hardware_configuration_unchanged=True,SRAM_profile_address='0x2dc00',
    preserved_previous_bytes=len(old)-12,ARM_emulation_verified=False,hardware_boot_verified=False)
(folder/'loader.toc0.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('BOOT_PROFILE_LOADER_BUILT',manifest['image_sha256'],patches)
