"""Exercise the pin-mux width trial and actual word CRC before installation."""
import hashlib
import json
from pathlib import Path
import random
import struct
import sys
import zlib

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'build/host-unicorn'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn import arm_const as arm
folder=root/'build/boot-fast'
base=(root/'tools/verify_boot_wide_emulation.py').read_text()
start=base.index('cases = ')
end=base.index("path = folder/'loader.toc0.json'")
trial=base[start:end]
trial=trial.replace('0x4c300','0x4c500').replace('    uc.mem_map(0x04022000, 0x1000)',
    '    uc.mem_map(0x04022000, 0x1000)\n    uc.mem_map(0x02000000, 0x1000)')
trial=trial.replace('delays=0)', 'delays=0, pin1=0xa5a5a5a5, pin2=0x12345670)')
trial=trial.replace('        assert size == 4\n        values',
    '        assert size == 4\n        values')
trial=trial.replace('0x02001838:0x80000000}',
    '0x02001838:0x80000000, 0x02000060:0x33333333,\n                  0x02000064:state["pin1"], 0x02000068:state["pin2"]}')
trial=trial.replace('        assert address == 0x0402200c and size == 4 and value == 2',
    '''        if address in (0x02000064,0x02000068):
            key='pin1' if address==0x02000064 else 'pin2'
            mask=0xfff0f000 if key=='pin1' else 0xf
            assert (value&~mask)==(state[key]&~mask)
            state[key]=value
            return
        assert address == 0x0402200c and size == 4 and value == 2
        assert state['pin1']==(0xa5a5a5a5&~0xfff0f000)|0x33303000
        assert state['pin2']==0x12345673''')
trial=trial.replace('((0x04022000, 0x04022fff),',
    '((0x02000000,0x02000fff),(0x04022000, 0x04022fff),')
trial=trial.replace("assert state['init_calls'] == 2 and state['width'] == 0",
    "assert state['init_calls'] == 2 and state['width'] == 0\n        assert state['pin1']==0xa5a5a5a5 and state['pin2']==0x12345670")
namespace=dict(globals())
namespace.update(binary=(folder/'loader.bin').read_bytes())
from unicorn.arm_const import *
namespace.update({k:v for k,v in vars(arm).items() if k.startswith('UC_ARM_REG_')})
exec(compile(trial,'pin-mux-width-emulation','exec'),namespace)
width_results=namespace['results']
binary=(folder/'loader.bin').read_bytes()
rng=random.Random(523)
crc_results=[]
for offset in (0,1,2,3):
    for pattern in range(16):
        uc=Uc(UC_ARCH_ARM,UC_MODE_ARM);uc.mem_map(0x20000,0x40000);uc.mem_write(0x44000,binary)
        payload=(bytes([pattern])*512 if pattern<4 else rng.randbytes(512))
        seed=rng.getrandbits(32);address=0x31000+offset;uc.mem_write(address,payload)
        reads=[]
        def read(m,access,addr,size,value,_):
            assert address<=addr and addr+size<=address+512
            reads.append((addr,size))
        uc.hook_add(UC_HOOK_MEM_READ,read,begin=0x31000,end=0x31fff)
        def write(m,access,addr,size,value,_):
            assert 0x2c000<=addr and addr+size<=0x2d000
        uc.hook_add(UC_HOOK_MEM_WRITE,write)
        saved=[getattr(arm,'UC_ARM_REG_R'+str(i)) for i in range(4,12)]
        uc.reg_write(arm.UC_ARM_REG_CPSR,0x1d3);uc.reg_write(arm.UC_ARM_REG_SP,0x2d000)
        uc.reg_write(arm.UC_ARM_REG_LR,0x5f000)
        for i,reg in enumerate(saved):uc.reg_write(reg,0x53240000+i)
        uc.reg_write(arm.UC_ARM_REG_R0,seed);uc.reg_write(arm.UC_ARM_REG_R1,address)
        uc.emu_start(0x4be00,0x5f000,count=30000)
        assert uc.reg_read(arm.UC_ARM_REG_PC)==0x5f000
        assert uc.reg_read(arm.UC_ARM_REG_R0)==zlib.crc32(payload,seed^0xffffffff)^0xffffffff
        assert [uc.reg_read(reg) for reg in saved]==[0x53240000+i for i in range(8)]
        assert uc.reg_read(arm.UC_ARM_REG_SP)==0x2d000 and bytes(uc.mem_read(address,512))==payload
        assert len(reads)==(128 if offset==0 else 512)
        assert all(size==(4 if offset==0 else 1) for _,size in reads)
        crc_results.append(dict(alignment=offset,pattern=pattern,status='PASS',input_reads=len(reads)))
path=folder/'loader.toc0.json';manifest=json.loads(path.read_text())
manifest.update(ARM_emulation_verified=True,emulation=width_results,CRC_emulation=crc_results)
path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
(root/'evidence/boot-fast-pins-word-emulation.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('BOOT_FAST_PIN_TRIAL_13_FAILURE_PATHS_AND_64_CRC_PATTERNS_PASS',manifest['image_sha256'])
