"""Package the signed image, authenticated asset and exact runtime delta."""
import hashlib,json,tarfile,struct,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'build/boot-logo'
m=json.loads((out/'loader.toc0.json').read_text());assert m['ARM_emulation_verified']
sys.path.insert(0,str(root/'build/host-unicorn'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM
from unicorn.arm_const import UC_ARM_REG_CPSR,UC_ARM_REG_R3
black=next(p for p in m['patches'] if p['old']==0xe3a030ff)
probe=Uc(UC_ARCH_ARM,UC_MODE_ARM);probe.mem_map(0x44000,0xc000)
probe.mem_write(0x44000,(out/'sram-loader.bin').read_bytes());probe.reg_write(UC_ARM_REG_CPSR,0x1d3)
probe.emu_start(black['address'],black['address']+4,count=1)
assert probe.reg_read(UC_ARM_REG_R3)==0x10000000
m['pre_DRAM_black_no_color_bytes_ARM_verified']=True
(out/'loader.toc0.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
names=('loader.toc0','loader.toc0.json','payload.bin','guard-files.json','dram-runtime.py','rtc-runtime.py',
       'pmic-runtime.py','handoff.py','linux-bundle.json','board.dtb','dtb-sectors.bin','active-header.bin','splash-preview.png')
with tarfile.open(root/'build/boot-logo-stage.tar.gz','w:gz') as archive:
    for name in names:archive.add(out/name,arcname=name)
print('BOOT_LOGO_STAGE_PACKAGED',m['image_sha256'],flush=True)
