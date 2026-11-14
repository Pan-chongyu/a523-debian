"""Append a reversible qualified CPU boost to the current full early-panel image."""
import hashlib,json,struct,subprocess
from pathlib import Path
from make_toc0 import build
root=Path(__file__).resolve().parents[1]
folder=root/'build/boot-cpu-performance';folder.mkdir(exist_ok=True)
assert not (folder/'loader.toc0').exists()
subprocess.run(['wsl','-d','Ubuntu-22.04','--','sh','/mnt/c/Users/pan75/Documents/ChatGPT/A523适配debian/tools/build_boot_cpu_performance.sh'],check=True)
base=root/'build/boot-panel-early-v2';old=(base/'loader.bin').read_bytes()
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha((base/'loader.toc0').read_bytes())=='1c2ce9324aae67cf5747c36249db0785c74d52c4094e4e735e37217f60800b41'
symbols={p[2]:int(p[0],16) for s in (folder/'cpu-hook.symbols.txt').read_text().splitlines() if len(p:=s.split())==3 and p[1] in ('T','t')}
hook=(folder/'cpu-hook.bin').read_bytes();assert 0<len(hook)<=0xe80
new=bytearray(old);patches=[]
for address,was,symbol,link in ((0x444a0,0xeb002096,'boot_cpu_performance_init',True),
        (0x4466c,0xeafffe72,'boot_cpu_performance_handoff',False),
        (0x445cc,0xe8bd8ff0,'boot_cpu_performance_failure',False)):
    offset=address-0x44000;assert struct.unpack_from('<I',old,offset)[0]==was
    entry=symbols[symbol];value=(0xeb000000 if link else 0xea000000)|(((entry-address-8)//4)&0xffffff)
    struct.pack_into('<I',new,offset,value)
    patches.append(dict(address=address,old=was,new=value,entry=entry,symbol=symbol))
allowed={i for p in patches for i in range(p['address']-0x44000,p['address']-0x44000+4)}
assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(new,old)))
new+=bytes(0x4e200-0x44000-len(new))+hook
assert len(new)+0xf80<=49152
(folder/'loader.bin').write_bytes(new);build(bytes(new),0x44000,folder/'loader.toc0')
manifest=json.loads((folder/'loader.toc0.json').read_text())
manifest.update(profile='qualified-1416MHz-1150mV-during-SRAM-load',previous_toc0_sha256=sha((base/'loader.toc0').read_bytes()),
    previous_loader_sha256=sha(old),loader_sha256=sha(new),patches=patches,hook_bytes=len(hook),
    original_early_panel_and_all_payload_CRC_retained=True,after_exact_CID_and_DRAM=True,
    CPUA_DCDC1_only=True,CPUB_DRAM_DSU_GPU_unchanged=True,restore_before_TFA_and_failure=True,
    SRAM_receipt_address='0x2d500',ARM_emulation_verified=False,hardware_boot_verified=False)
(folder/'loader.toc0.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('BOOT_CPU_PERFORMANCE_IMAGE_BUILT',json.dumps(manifest),flush=True)
