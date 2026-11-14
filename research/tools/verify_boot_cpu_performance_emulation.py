"""Execute the patched ARM boost and both exact cleanup paths with I2C/PLL failures."""
import hashlib,json,struct,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'build/host-unicorn'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
folder=root/'build/boot-cpu-performance';binary=(folder/'loader.bin').read_bytes()
symbols={p[2]:int(p[0],16) for s in (folder/'cpu-hook.symbols.txt').read_text().splitlines() if len(p:=s.split())==3}
registers=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,
    UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC]
cases=('normal','DVM_bit_preserved','wrong_SID','unknown_PLL','unknown_mux','wrong_PMIC_ID',
    'unknown_voltage','TWI_timeout','raise_readback_failure','PLL_update_timeout','PLL_lock_timeout',
    'CID_mismatch','emmc_init_failure','common_failure_exit','restore_lock_failure','lower_readback_failure')
results=[]
for case in cases:
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for base,size in ((0x20000,0x40000),(0x08817000,0x1000),(0x07081000,0x1000),(0x03006000,0x1000),(0x02050000,0x1000),(0x07090000,0x1000)):u.mem_map(base,size)
    u.mem_write(0x44000,binary)
    original_mv=0xa8 if case=='DVM_bit_preserved' else 41 if case=='unknown_voltage' else 40
    data=dict(pll=0xf8801400,mux=0x03000305,pmic={3:0xff,0x83:original_mv},bus=False,
        phase='address',status=0,tx=0,reg=0,writes=[],pmic_writes=[],delays=[],ticks=2400000,
        calls=0,restoring=False,fatal=False,clock_raised=False)
    if case=='unknown_PLL':data['pll']=0xf8801500
    if case=='unknown_mux':data['mux']=0x02000305
    if case=='wrong_PMIC_ID':data['pmic'][3]=0x49
    initial=(data['pll'],data['mux'])
    error=-9 if case=='CID_mismatch' else -1 if case=='emmc_init_failure' else 0
    def put(a,v):u.mem_write(a,struct.pack('<I',v&0xffffffff))
    def read(machine,access,address,size,value,user):
        assert size==4
        if address==0x08817004:put(address,data['pll'])
        elif address==0x08817060:put(address,data['mux'])
        elif address==0x03006248:put(address,0x38 if case=='wrong_SID' else 0x48)
        elif address==0x0708140c:put(address,0x40 if case=='TWI_timeout' else 0x48)
        elif address==0x07081410:put(address,data['status'])
        elif address==0x07081408 and data['phase']=='read':put(address,data['pmic'].get(data['reg'],0))
        else:raise AssertionError((case,'unexpected MMIO read',hex(address)))
    def write(machine,access,address,size,value,user):
        assert size==4
        data['writes'].append((address,value))
        if address==0x08817004:
            n=(value>>8)&255
            if n==59:
                assert data['pmic'][0x83]&127==65,'PLL raised before voltage settles'
                data['clock_raised']=True
            data['pll']=value
            if not(case=='PLL_update_timeout' and n==59):data['pll']&=~(1<<26)
            locked=not((case=='PLL_lock_timeout' and n==59) or (case=='restore_lock_failure' and data['restoring']))
            if locked and value&(1<<29):data['pll']|=1<<28
            else:data['pll']&=~(1<<28)
        elif address==0x08817060:data['mux']=value
        elif address==0x07081408:data['tx']=value
        elif address==0x0708140c:
            if value==0x68:
                data['status']=0x10 if data['bus'] else 8;data['bus']=True;data['phase']='address'
            elif value==0x58:data['bus']=False;data['phase']='address'
            elif value==0x48:
                if data['phase']=='address':
                    assert data['tx'] in (0x68,0x69)
                    data['status']=0x40 if data['tx']==0x69 else 0x18
                    data['phase']='read' if data['tx']==0x69 else 'register'
                elif data['phase']=='register':data['reg']=data['tx'];data['status']=0x28;data['phase']='value'
                elif data['phase']=='value':
                    assert data['reg']==0x83 and 40<=data['tx']&127<=65
                    assert data['tx']&128==original_mv&128
                    if (data['tx']&127)<(data['pmic'][0x83]&127):assert (data['pll']>>8)&255==20
                    data['pmic_writes'].append(data['tx'])
                    fail=(case=='raise_readback_failure' and not data['restoring'] and data['tx']&127==43) or (case=='lower_readback_failure' and data['restoring'])
                    if not fail:data['pmic'][0x83]=data['tx']
                    data['status']=0x28
                elif data['phase']=='read':data['status']=0x58
        else:raise AssertionError((case,'unexpected MMIO write',hex(address)))
    def code(machine,address,size,user):
        if address==0x4c700:
            data['calls']+=1;machine.reg_write(UC_ARM_REG_R0,error&0xffffffff)
            machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR))
        elif address==0x44134:
            delay=machine.reg_read(UC_ARM_REG_R0);data['delays'].append(delay);data['ticks']+=delay*24
            machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR))
        elif address in (0x444a4,0x4403c,0x5f000):machine.emu_stop()
        elif address==symbols['boot_cpu_restore']:data['restoring']=True
        elif address==symbols['fatal']:data['fatal']=True;machine.emu_stop()
        else:
            instruction=struct.unpack('<I',machine.mem_read(address,4))[0]
            if instruction&0xfff00fff==0xec500f0e:
                machine.reg_write(registers[(instruction>>12)&15],data['ticks']&0xffffffff)
                machine.reg_write(registers[(instruction>>16)&15],data['ticks']>>32)
                machine.reg_write(UC_ARM_REG_PC,address+4)
    u.hook_add(UC_HOOK_CODE,code)
    for start,end in ((0x08817000,0x08817fff),(0x07081000,0x07081fff),(0x03006000,0x03006fff)):
        u.hook_add(UC_HOOK_MEM_READ,read,begin=start,end=end);u.hook_add(UC_HOOK_MEM_WRITE,write,begin=start,end=end)
    u.reg_write(UC_ARM_REG_CPSR,0x1d3);u.reg_write(UC_ARM_REG_SP,0x2d000);u.reg_write(UC_ARM_REG_LR,0x5f000)
    saved=registers[4:12]
    for i,reg in enumerate(saved):u.reg_write(reg,0x54321000+i)
    u.emu_start(0x444a0,0x60000,timeout=20_000_000,count=2_000_000)
    assert u.reg_read(UC_ARM_REG_PC)==0x444a4 and u.reg_read(UC_ARM_REG_R0)==error&0xffffffff,case
    assert u.reg_read(UC_ARM_REG_SP)==0x2d000
    assert [u.reg_read(r) for r in saved]==[0x54321000+i for i in range(8)]
    receipt=lambda:list(struct.unpack('<16I',u.mem_read(0x2d500,64)))
    successful=case in ('normal','DVM_bit_preserved','common_failure_exit','restore_lock_failure','lower_readback_failure')
    if successful:
        assert receipt()[2:4]==[2,1] and receipt()[8:10]==[1416000,1150],(case,receipt())
        assert (data['pll']>>8)&255==59 and data['pmic'][0x83]&127==65
    elif case in ('PLL_update_timeout','PLL_lock_timeout','raise_readback_failure'):
        assert receipt()[2:4]==[4,0] and data['pmic'][0x83]==original_mv and (data['pll']>>8)&255==20
    else:
        assert not data['pmic_writes'] and not [a for a,_ in data['writes'] if a in (0x08817004,0x08817060)]
        assert (data['pll'],data['mux'])==initial,case
    if case=='common_failure_exit':
        frame=[0x11111111+i for i in range(8)]+[0x5f000]
        u.mem_write(0x2c000,struct.pack('<9I',*frame));u.reg_write(UC_ARM_REG_SP,0x2c000)
        u.reg_write(UC_ARM_REG_R0,0xdeadbeef)
        u.emu_start(0x445cc,0x60000,timeout=20_000_000,count=2_000_000)
        assert u.reg_read(UC_ARM_REG_PC)==0x5f000 and u.reg_read(UC_ARM_REG_SP)==0x2c024
        assert u.reg_read(UC_ARM_REG_R0)==0xdeadbeef and [u.reg_read(r) for r in saved]==frame[:8]
    else:
        u.reg_write(UC_ARM_REG_R0,0x54000);u.reg_write(UC_ARM_REG_LR,0x5f000)
        u.emu_start(0x4466c,0x60000,timeout=20_000_000,count=2_000_000)
        if case in ('restore_lock_failure','lower_readback_failure'):assert data['fatal']
        else:assert u.reg_read(UC_ARM_REG_PC)==0x4403c and u.reg_read(UC_ARM_REG_R0)==0x54000
    if successful and not data['fatal']:
        assert receipt()[2:4]==[4,0] and receipt()[12]==original_mv
        assert (data['pll']>>8)&255==20 and data['mux']==initial[1] and data['pmic'][0x83]==original_mv
    results.append(dict(case=case,status='PASS',receipt=receipt(),PMIC_writes=data['pmic_writes'],
        fatal_instead_of_unsafe_handoff=data['fatal'],only_CPUA_clock_and_DCDC1_written=True))
manifest=json.loads((folder/'loader.toc0.json').read_text())
manifest.update(ARM_emulation_verified=True,emulation=results,real_TWI_state_machine_and_PLL_handshakes_executed=True)
(folder/'loader.toc0.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
(root/'evidence/boot-cpu-performance-emulation.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('BOOT_CPU_PERFORMANCE_ACTUAL_ARM_GUARDS_AND_RESTORATION_PASS',len(results),flush=True)
