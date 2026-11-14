"""Execute AArch32 CRC32W with Unicorn's ARMv8 model and compare with zlib."""
import json
from pathlib import Path
import random
import struct
import sys
import zlib
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'build/host-unicorn'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn import arm_const as arm
folder=root/'build/boot-hwcrc';binary=(folder/'loader.bin').read_bytes()
results=[];rng=random.Random(523)
for supported in (False,True):
    for alignment in range(4):
        for pattern in range(16):
            uc=Uc(UC_ARCH_ARM,UC_MODE_ARM);uc.ctl_set_cpu_model(arm.UC_CPU_ARM_MAX)
            uc.mem_map(0x20000,0x40000);uc.mem_write(0x44000,binary)
            address=0x31000+alignment;payload=bytes([pattern])*512 if pattern<4 else rng.randbytes(512)
            seed=rng.getrandbits(32);uc.mem_write(address,payload)
            feature=0x11110 if supported else 0x1110
            steps=dict(crc_instructions=0)
            def code(m,addr,size,_):
                ins=struct.unpack('<I',m.mem_read(addr,4))[0]
                if ins&0xffff0fff==0xee100fb2:
                    reg=getattr(arm,'UC_ARM_REG_R'+str((ins>>12)&15))
                    m.reg_write(reg,feature);m.reg_write(arm.UC_ARM_REG_PC,addr+4)
                if ins&0xfff00ff0==0xe1400040:
                    steps['crc_instructions']+=1
            def write(m,access,addr,size,value,_):
                assert 0x2c000<=addr and addr+size<=0x2d000 or 0x2dfc0<=addr and addr+size<=0x2dfd0
            uc.hook_add(UC_HOOK_CODE,code);uc.hook_add(UC_HOOK_MEM_WRITE,write)
            uc.reg_write(arm.UC_ARM_REG_CPSR,0x1d3);uc.reg_write(arm.UC_ARM_REG_SP,0x2d000)
            uc.reg_write(arm.UC_ARM_REG_LR,0x5f000)
            saved=[getattr(arm,'UC_ARM_REG_R'+str(i)) for i in range(4,12)]
            for i,reg in enumerate(saved):uc.reg_write(reg,0x12340000+i)
            uc.reg_write(arm.UC_ARM_REG_R0,seed);uc.reg_write(arm.UC_ARM_REG_R1,address)
            uc.emu_start(0x4be00,0x5f000,count=30000)
            assert uc.reg_read(arm.UC_ARM_REG_PC)==0x5f000
            assert uc.reg_read(arm.UC_ARM_REG_R0)==zlib.crc32(payload,seed^0xffffffff)^0xffffffff
            assert [uc.reg_read(reg) for reg in saved]==[0x12340000+i for i in range(8)]
            assert uc.reg_read(arm.UC_ARM_REG_SP)==0x2d000 and bytes(uc.mem_read(address,512))==payload
            receipt=list(struct.unpack('<4I',uc.mem_read(0x2dfc0,16)))
            hardware=supported and alignment==0
            assert steps['crc_instructions']==(128 if hardware else 0),steps
            assert receipt==[0xa523cc01,feature,int(hardware),int(hardware)],receipt
            results.append(dict(supported=supported,alignment=alignment,pattern=pattern,status='PASS',
                real_CRC32W_executed=hardware,software_fallback_used=not hardware))
path=folder/'loader.toc0.json';manifest=json.loads(path.read_text())
manifest.update(ARM_emulation_verified=True,emulation=results)
path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
(root/'evidence/boot-hwcrc-emulation.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('AARCH32_HARDWARE_CRC_AND_SOFTWARE_FALLBACK_128_CASES_PASS',manifest['image_sha256'])
