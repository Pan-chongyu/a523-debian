"""Append a pre-training panel hook while preserving the full verified boot chain."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from make_toc0 import build

root=Path(__file__).resolve().parents[1]
folder=root/'build/boot-panel-early-v2'
folder.mkdir(exist_ok=True)
assert not (folder/'loader.toc0').exists()
subprocess.run(['wsl','-d','Ubuntu-22.04','--','sh',
    '/mnt/c/Users/pan75/Documents/ChatGPT/A523适配debian/tools/build_boot_panel.sh'],check=True)
base=root/'build/boot-hwcrc'
old=(base/'loader.bin').read_bytes()
previous=json.loads((base/'loader.toc0.json').read_text())
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha((base/'loader.toc0').read_bytes())==previous['image_sha256']=='50537c7ff9d9b20461c0a1181f3b4f04240e63be7aece9f49ba1ce6c18bc0c9b'
assert sha(old)==previous['loader_sha256'] and len(old)==36508
hook=(folder/'panel-hook.bin').read_bytes()
entry=struct.unpack_from('<I',(folder/'panel-hook.elf').read_bytes(),24)[0]
assert 0x4d000<=entry<0x4e000 and 0<len(hook)<=8192
address=0x44168
offset=address-0x44000
was=struct.unpack_from('<I',old,offset)[0]
assert was==0xea001e35
assert json.loads((root/'build/dram-boot-voltage/HOOK_CHANGE.json').read_text())['hook_entry']=='0x4ba44'
value=0xea000000|(((entry-address-8)//4)&0xffffff)
new=bytearray(old)
struct.pack_into('<I',new,offset,value)
assert new[:offset]==old[:offset] and new[offset+4:]==old[offset+4:]
new+=bytes(0x4d000-0x44000-len(new))+hook
assert 0x44000+len(new)<0x54000
(folder/'loader.bin').write_bytes(new)
build(bytes(new),0x44000,folder/'loader.toc0')
manifest=json.loads((folder/'loader.toc0.json').read_text())
manifest.update(previous_toc0_sha256=previous['image_sha256'],previous_loader_sha256=sha(old),
    loader_sha256=sha(new),patches=[dict(address=address,old=was,new=value,entry=entry)],
    hook_entry=hex(entry),hook_bytes=len(hook),hook_address='0x4d000',
    SRAM_receipt='0x2d200',before_DRAM_training=True,original_voltage_hook_called_first=True,
    full_DRAM_and_original_MMC_CRC_BL31_kernel_preserved=True,DRAM_access_by_panel=False,
    only_PMIC_write_register='AXP717 0x91 known CLDO4 enable bit',
    qualified_DSI_150MHz_parent=True,PERIPH0_VIDEO0_PLL_only=True,
    CPU_DDR_GPU_PLL_unchanged=True,backlight_percent=20,receipt_version=2,
    display_failure_nonfatal_with_register_rollback=True,
    raw_boot_hash_scope='Full TOC0 length from its validated header, up to 49152 bytes',
    ARM_emulation_verified=False,hardware_boot_verified=False)
assert manifest['image_bytes']==49152
(folder/'loader.toc0.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('PRE_DRAM_EARLY_PANEL_CANDIDATE_BUILT',json.dumps(manifest),flush=True)
