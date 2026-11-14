"""Execute the real patched ARM branches, checking ABI, CRC, counters and failures."""
import hashlib
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
regs=[getattr(arm,'UC_ARM_REG_R'+str(i)) for i in range(13)]
folder=root/'build/boot-profile'
binary=(folder/'loader.bin').read_bytes()
results=[]
for case in ('normal','init_failure','read_failure','CRC_unaligned','counter_carry'):
    uc=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    uc.mem_map(0x20000,0x40000)
    for addr in (0x8817000,0x2001000,0x4022000): uc.mem_map(addr,4096)
    uc.mem_write(0x44000,binary)
    for addr,value in ((0x8817004,0x48801400),(0x8817060,0x3000000),
                       (0x2001838,0x80000000),(0x402200c,0)):
        uc.mem_write(addr,struct.pack('<I',value))
    clock=[(1<<32)-200 if case=='counter_carry' else 120000000]
    calls=[]
    init_error=-9 if case=='init_failure' else 0
    read_error=-2 if case=='read_failure' else 0
    def code(m,address,size,_):
        clock[0]+=3
        ins=struct.unpack('<I',m.mem_read(address,4))[0]
        if ins&0xfff00fff==0xec500f0e:
            m.reg_write(regs[(ins>>12)&15],clock[0]&0xffffffff)
            m.reg_write(regs[(ins>>16)&15],clock[0]>>32)
            m.reg_write(arm.UC_ARM_REG_PC,address+4)
        elif ins==0xee1e3f10:
            m.reg_write(regs[3],24000000)
            m.reg_write(arm.UC_ARM_REG_PC,address+4)
        elif address in (0x4c300,0x44bac):
            calls.append(address)
            if address==0x4c300: result=init_error
            else:
                assert m.reg_read(regs[0])==4096 and m.reg_read(regs[1])==0x31000
                result=read_error
                if not result: m.mem_write(0x31000,bytes(range(256))*2)
            m.reg_write(regs[0],result&0xffffffff)
            m.reg_write(arm.UC_ARM_REG_PC,m.reg_read(arm.UC_ARM_REG_LR))
        elif address in (0x444a4,0x5f000):m.emu_stop()
    writes=[]
    def write(m,access,address,size,value,_):
        assert 0x2dc00<=address and address+size<=0x2dc50 or 0x2c000<=address and address+size<=0x2d000
        writes.append(address)
    uc.hook_add(UC_HOOK_CODE,code)
    uc.hook_add(UC_HOOK_MEM_WRITE,write)
    def execute(entry,r0=0,r1=0):
        uc.reg_write(arm.UC_ARM_REG_CPSR,0x1d3)
        uc.reg_write(arm.UC_ARM_REG_SP,0x2d000)
        uc.reg_write(arm.UC_ARM_REG_LR,0x5f000)
        for i in range(4,12):uc.reg_write(regs[i],0x44330000+i)
        uc.reg_write(regs[0],r0);uc.reg_write(regs[1],r1)
        uc.emu_start(entry,0x5f004,count=200000)
        assert uc.reg_read(arm.UC_ARM_REG_PC) in (0x444a4,0x5f000)
        assert uc.reg_read(arm.UC_ARM_REG_SP)==0x2d000
        assert [uc.reg_read(regs[i]) for i in range(4,12)]==[0x44330000+i for i in range(4,12)]
        return uc.reg_read(regs[0])
    assert execute(0x444a0)==init_error&0xffffffff
    assert execute(0x44cf0,4096,0x31000)==read_error&0xffffffff
    rng=random.Random(523)
    offset=1 if case=='CRC_unaligned' else 0
    for i in range(16):
        data=rng.randbytes(512);seed=rng.getrandbits(32)
        uc.mem_write(0x32000+offset,data)
        assert execute(0x44454,seed,0x32000+offset)==zlib.crc32(data,seed^0xffffffff)^0xffffffff
    fields=struct.unpack('<II5Q7Ii',uc.mem_read(0x2dc00,80))
    magic,version,start,end,read_ticks,crc_ticks,last,reads,crcs,pll,mux,mmc,width,hz,error=fields
    assert (magic,version,reads,crcs,pll,mux,mmc,width,hz,error)==(
        0xa523f101,1,1,16,0x48801400,0x3000000,0x80000000,0,24000000,read_error)
    assert start<end<last and 0<read_ticks<crc_ticks
    assert calls==[0x4c300,0x44bac]
    results.append(dict(case=case,status='PASS',ABI_preserved=True,CRC_payload_verified=16,
                        profile_writes_only_to_reserved_SRAM=True,hardware_writes=0))
manifest_path=folder/'loader.toc0.json'
manifest=json.loads(manifest_path.read_text())
manifest.update(ARM_emulation_verified=True,emulation=results)
manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
(root/'evidence/boot-profile-emulation.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('BOOT_PROFILE_REAL_ARM_ABI_CRC_COUNTERS_PASS',results)
