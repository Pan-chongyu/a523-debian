"""Retain the measured wide reader and replace only the pure CRC entry."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from make_toc0 import build
root=Path(__file__).resolve().parents[1]
folder=root/'build/boot-hwcrc';folder.mkdir(exist_ok=True)
assert not (folder/'loader.toc0').exists()
subprocess.run(['wsl','-d','Ubuntu-22.04','--','sh',
    '/mnt/c/Users/pan75/Documents/ChatGPT/A523适配debian/tools/build_boot_hwcrc.sh'],check=True)
base=root/'build/boot-fast';old=(base/'loader.bin').read_bytes()
previous=json.loads((base/'loader.toc0.json').read_text());sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha((base/'loader.toc0').read_bytes())==previous['image_sha256']=='319cdcc46804ce7136b5f00479dd6c320bc561340ea285655293de3665ab179e'
assert sha(old)==previous['loader_sha256']
entry=struct.unpack_from('<I',(folder/'hwcrc-hook.elf').read_bytes(),24)[0]
hook=(folder/'hwcrc-hook.bin').read_bytes();assert entry==0x4ce00 and len(hook)<=512
new=bytearray(old);address=0x4be00;offset=address-0x44000
was=struct.unpack_from('<I',old,offset)[0];assert was==previous['patches'][1]['new']
value=0xea000000|(((entry-address-8)//4)&0xffffff)
struct.pack_into('<I',new,offset,value)
assert new[:offset]==old[:offset] and new[offset+4:len(old)]==old[offset+4:]
new+=bytes(entry-0x44000-len(new))+hook
assert len(new)+0xf80<=40960
(folder/'loader.bin').write_bytes(new);build(bytes(new),0x44000,folder/'loader.toc0')
manifest=json.loads((folder/'loader.toc0.json').read_text())
manifest.update(previous_toc0_sha256=previous['image_sha256'],previous_loader_sha256=sha(old),
    loader_sha256=sha(new),patches=[dict(address=address,old=was,new=value,entry=entry)],
    hook_entry=hex(entry),hook_bytes=len(hook),CRC_polynomial_seed_unchanged=True,
    ID_ISAR5_CRC32_guard=True,software_fallback_retained=True,no_hardware_configuration_writes=True,
    ARM_emulation_verified=False,hardware_boot_verified=False)
(folder/'loader.toc0.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('HW_CRC_GUARDED_LOADER_BUILT',manifest['image_sha256'],len(new),len(hook))
