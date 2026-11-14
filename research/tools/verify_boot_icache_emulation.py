"""Check real ARM CP15 writes and exact restoration for every supported state."""
import json
from pathlib import Path
import struct
import sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'build/host-unicorn'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn import arm_const as arm
folder=root/'build/boot-icache';binary=(folder/'loader.bin').read_bytes()
regs=[getattr(arm,'UC_ARM_REG_R'+str(i)) for i in range(13)]
results=[]
for case,initial in (('normal',0x00c50078),('different_other_bits',0x30c50878),
                     ('already_enabled',0x00c51078),('MMU_enabled',0x00c50079),
                     ('data_cache_enabled',0x00c5007c),('init_failure',0x00c50078),
                     ('load_CRC_failure',0x00c50078)):
    uc=Uc(UC_ARCH_ARM,UC_MODE_ARM);uc.mem_map(0x20000,0x40000);uc.mem_write(0x44000,binary)
    state=dict(control=initial,writes=[],invalidations=[],init_calls=0,handoff=None)
    def code(m,address,size,_):
        ins=struct.unpack('<I',m.mem_read(address,4))[0]
        if ins&0xffff0fff==0xee110f10:
            m.reg_write(regs[(ins>>12)&15],state['control'])
            m.reg_write(arm.UC_ARM_REG_PC,address+4)
        elif ins&0xffff0fff==0xee010f10:
            value=m.reg_read(regs[(ins>>12)&15]);state['writes'].append(value)
            assert value in (initial,initial|4096)
            assert (value&~4096)==(initial&~4096)
            state['control']=value;m.reg_write(arm.UC_ARM_REG_PC,address+4)
        elif ins&0xffff0fff in (0xee070f15,0xee070fd5):
            state['invalidations'].append(ins&0xffff0fff)
            m.reg_write(arm.UC_ARM_REG_PC,address+4)
        elif address==0x4c700:
            state['init_calls']+=1
            m.reg_write(regs[0],0xfffffff7 if case=='init_failure' else 0)
            m.reg_write(arm.UC_ARM_REG_PC,m.reg_read(arm.UC_ARM_REG_LR))
        elif address==0x444a4:m.emu_stop()
        elif address==0x4403c:
            state['handoff']=m.reg_read(regs[0]);m.emu_stop()
        elif address==0x5f000:m.emu_stop()
    def write(m,access,address,size,value,_):
        assert 0x2c000<=address and address+size<=0x2d000 or 0x2dfc0<=address and address+size<=0x2dfd8
    uc.hook_add(UC_HOOK_CODE,code);uc.hook_add(UC_HOOK_MEM_WRITE,write)
    uc.reg_write(arm.UC_ARM_REG_CPSR,0x1d3);uc.reg_write(arm.UC_ARM_REG_SP,0x2d000)
    for i in range(4,12):uc.reg_write(regs[i],0xa5230000+i)
    uc.emu_start(0x444a0,0x5f000,count=10000)
    assert uc.reg_read(arm.UC_ARM_REG_PC)==0x444a4
    assert uc.reg_read(arm.UC_ARM_REG_SP)==0x2d000
    assert [uc.reg_read(regs[i]) for i in range(4,12)]==[0xa5230000+i for i in range(4,12)]
    if case=='init_failure':
        assert state['writes']==state['invalidations']==[]
        assert uc.reg_read(regs[0])==0xfffffff7
    else:
        assert uc.reg_read(regs[0])==0
        if case=='load_CRC_failure':
            frame=[0xa5230000+i for i in range(4,12)]+[0x5f000]
            uc.mem_write(0x2d000-36,struct.pack('<9I',*frame))
            uc.reg_write(arm.UC_ARM_REG_SP,0x2d000-36)
            uc.reg_write(regs[0],0xfffffff2)
            uc.emu_start(0x445cc,0x5f004,count=10000)
            assert uc.reg_read(arm.UC_ARM_REG_PC)==0x5f000
            assert uc.reg_read(arm.UC_ARM_REG_SP)==0x2d000
            assert uc.reg_read(regs[0])==0xfffffff2
            assert [uc.reg_read(regs[i]) for i in range(4,12)]==frame[:8]
            assert state['handoff'] is None
        else:
            uc.reg_write(regs[0],0x54000)
            uc.emu_start(0x4466c,0x5f000,count=10000)
            assert state['handoff']==0x54000
        assert state['control']==initial
        receipt=list(struct.unpack('<6I',uc.mem_read(0x2dfc0,24)))
        expected=3 if initial&5 else 2 if initial&4096 else 4
        assert receipt==[0xa5231c01,expected,initial,initial if expected!=4 else initial|4096,initial,
                         0 if case=='load_CRC_failure' else 0x54000]
        assert state['writes']==([initial|4096,initial] if expected==4 else [])
        assert len(state['invalidations'])==(4 if expected==4 else 0)
    assert state['init_calls']==1
    results.append(dict(case=case,status='PASS',initial=hex(initial),final=hex(state['control']),
        instruction_cache_control_writes=[hex(v) for v in state['writes']],MMU_data_cache_unchanged=True))
path=folder/'loader.toc0.json';manifest=json.loads(path.read_text())
manifest.update(ARM_emulation_verified=True,emulation=results)
path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
(root/'evidence/boot-icache-emulation.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('BOOT_ICACHE_SEVEN_REAL_ARM_GUARDS_AND_ALL_EXITS_RESTORE_PASS',results)
