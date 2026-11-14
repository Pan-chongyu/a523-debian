"""Retain the measured 8-bit reader and CRC, enable temporary instruction cache."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from make_toc0 import build
root=Path(__file__).resolve().parents[1]
folder=root/'build/boot-icache';folder.mkdir(exist_ok=True)
assert not (folder/'loader.toc0').exists()
subprocess.run(['wsl','-d','Ubuntu-22.04','--','sh',
    '/mnt/c/Users/pan75/Documents/ChatGPT/A523适配debian/tools/build_boot_icache.sh'],check=True)
base=root/'build/boot-fast';old=(base/'loader.bin').read_bytes()
previous=json.loads((base/'loader.toc0.json').read_text());sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha((base/'loader.toc0').read_bytes())==previous['image_sha256']=='319cdcc46804ce7136b5f00479dd6c320bc561340ea285655293de3665ab179e'
assert sha(old)==previous['loader_sha256']
symbols={p[2]:int(p[0],16) for s in (folder/'icache-hook.symbols.txt').read_text().splitlines()
    if len(p:=s.split())==3 and p[1] in ('T','t')}
hook=(folder/'icache-hook.bin').read_bytes()
first=min(symbols.values());assert first==0x4ce00 and len(hook)<=1024
new=bytearray(old);patches=[]
for address,was,symbol,link in ((0x444a0,0xeb002096,'boot_icache_init',True),
                              (0x4466c,0xeafffe72,'boot_icache_handoff',False),
                              (0x445cc,0xe8bd8ff0,'boot_icache_failure',False)):
    offset=address-0x44000;assert struct.unpack_from('<I',old,offset)[0]==was,hex(address)
    entry=symbols[symbol];value=(0xeb000000 if link else 0xea000000)|(((entry-address-8)//4)&0xffffff)
    struct.pack_into('<I',new,offset,value)
    patches.append(dict(address=address,old=was,new=value,entry=entry))
allowed={i for p in patches for i in range(p['address']-0x44000,p['address']-0x44000+4)}
assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(new,old)))
new+=bytes(first-0x44000-len(new))+hook
assert len(new)+0xf80<=40960
(folder/'loader.bin').write_bytes(new);build(bytes(new),0x44000,folder/'loader.toc0')
manifest=json.loads((folder/'loader.toc0.json').read_text())
manifest.update(previous_toc0_sha256=previous['image_sha256'],previous_loader_sha256=sha(old),
    loader_sha256=sha(new),patches=patches,hook_entry=hex(symbols['boot_icache_init']),hook_bytes=len(hook),
    instruction_cache_only=True,MMU_data_cache_voltage_clocks_unchanged=True,
    original_control_restored_before_handoff=True,SRAM_receipt_address='0x2dfc0',
    ARM_emulation_verified=False,hardware_boot_verified=False)
(folder/'loader.toc0.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('BOOT_ICACHE_RESTORING_LOADER_BUILT',manifest['image_sha256'],len(new),len(hook))
