"""Add Linux-matched data pin mux and word-read CRC to the measured loader."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from make_toc0 import build

root=Path(__file__).resolve().parents[1]
folder=root/'build/boot-fast';folder.mkdir(exist_ok=True)
assert not (folder/'loader.toc0').exists()
subprocess.run(['wsl','-d','Ubuntu-22.04','--','sh',
    '/mnt/c/Users/pan75/Documents/ChatGPT/A523适配debian/tools/build_boot_fast.sh'],check=True)
base=root/'build/boot-profile'
old=(base/'loader.bin').read_bytes();previous=json.loads((base/'loader.toc0.json').read_text())
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha((base/'loader.toc0').read_bytes())==previous['image_sha256']=='4ae89856592e7b95fde5d0b40e49a09255f9745470fa9cc22bc64a06319ac4bc'
assert sha(old)==previous['loader_sha256'] and previous['ARM_emulation_verified']
new=bytearray(old);patches=[]
for address,was,entry in ((0x444a0,0xeb002016,0x4c700),(0x4be00,0xe59fc020,0x4cb00)):
    offset=address-0x44000
    assert struct.unpack_from('<I',old,offset)[0]==was,hex(address)
    value=(0xeb000000 if address==0x444a0 else 0xea000000)|(((entry-address-8)//4)&0xffffff)
    struct.pack_into('<I',new,offset,value)
    patches.append(dict(address=address,old=was,new=value,entry=entry))
for part,entry,maximum in (('pins',0x4c700,1024),('word',0x4cb00,512)):
    hook=(folder/(part+'-hook.bin')).read_bytes()
    assert len(hook)<=maximum
    assert struct.unpack_from('<I',(folder/(part+'-hook.elf')).read_bytes(),24)[0]==entry
    new+=bytes(entry-0x44000-len(new))+hook
allowed={i for p in patches for i in range(p['address']-0x44000,p['address']-0x44000+4)}
assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(new,old)))
assert len(new)+0xf80<=40960
(folder/'loader.bin').write_bytes(new);build(bytes(new),0x44000,folder/'loader.toc0')
manifest=json.loads((folder/'loader.toc0.json').read_text())
manifest.update(previous_toc0_sha256=previous['image_sha256'],previous_loader_sha256=sha(old),
    loader_sha256=sha(new),patches=patches,hook_entry='0x4c700',
    hook_bytes=sum((folder/(p+'-hook.bin')).stat().st_size for p in ('pins','word')),
    bus_width=8,clock_voltage_timing_unchanged=True,SRAM_profile_address='0x2dc00',
    pins_match_qualified_Linux_DT=True,no_storage_data_writes=True,CRC_polynomial_seed_unchanged=True,
    ARM_emulation_verified=False,hardware_boot_verified=False)
(folder/'loader.toc0.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('MEASURED_BOOT_READER_AND_WORD_CRC_BUILT',manifest['image_sha256'],manifest['hook_bytes'])
