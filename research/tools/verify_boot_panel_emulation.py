"""Exercise the actual ARM early-panel hook, its I2C protocol and rollback paths."""
import hashlib
import json
from pathlib import Path
import struct
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'build/host-unicorn'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R4,UC_ARM_REG_R5,
    UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,
    UC_ARM_REG_R11,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_CPSR)

folder=root/'build/boot-panel-early-v2'
binary=(folder/'loader.bin').read_bytes()
manifest=json.loads((folder/'loader.toc0.json').read_text())
symbols={line.split()[2]:int(line.split()[0],16)
    for line in (folder/'panel-hook.symbols.txt').read_text().splitlines() if len(line.split())==3}
results=[]
cases=('normal','original_CLDO2_enabled','voltage_failure','PMIC_voltage_mismatch',
       'PMIC_enable_unknown','TWI_timeout','rail_write_failure','display_busy','PLL_timeout',
       'panel_ID_mismatch','LP_timeout','panel_not_awake','scan_stopped',
       'periph_timeout','video_parent_timeout','periph_pre_enabled','unexpected_live_periph')
successes=('normal','original_CLDO2_enabled','periph_pre_enabled')

for case in cases:
    uc=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for base,size in ((0x20000,0x40000),(0x02000000,0x6000),(0x02050000,0x1000),
                      (0x05500000,0x10000),(0x07081000,0x1000)):
        uc.mem_map(base,size)
    uc.mem_write(0x44000,binary)
    data=dict(pmic={0x9b:0x0d,0x9e:0x1c,0x91:0xd7 if case=='original_CLDO2_enabled' else 0xd5},
        pmic_writes=[],writes=[],delays=[],ticks=2400000,voltage_calls=[],bus=False,
        phase='address',reg=0,status=0,tx=0,command=0,video=False,line=0,backlight=False)
    if case=='PMIC_voltage_mismatch':data['pmic'][0x9b]=0x0c
    if case=='PMIC_enable_unknown':data['pmic'][0x91]=0x15
    def put(address,value):uc.mem_write(address,struct.pack('<I',value&0xffffffff))
    def get(address):return struct.unpack('<I',uc.mem_read(address,4))[0]
    # Unrelated mux/data bits must survive every attempt, including failures.
    initial={0x02000094:0x00000055,0x02000098:0x00550000,
        0x020000a0:0x01000005,0x02000158:0xabcd00ab,0x02000160:0x01000007}
    for address,value in initial.items():put(address,value)
    parents={0x02001020:0xf8216310 if case=='periph_pre_enabled' else
        0xf8216210 if case=='unexpected_live_periph' else 0,
        0x02001040:0}
    for address,value in parents.items():put(address,value)
    if case=='display_busy':put(0x02001b4c,2)

    def code(machine,address,size,user):
        if address==0x4ba44:
            data['voltage_calls'].append(machine.reg_read(UC_ARM_REG_R0))
            machine.reg_write(UC_ARM_REG_R0,0xffffffff if case=='voltage_failure' else 0)
            machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR))
        elif address==0x44134:
            delay=machine.reg_read(UC_ARM_REG_R0)
            data['delays'].append(delay);data['ticks']+=delay*24
            machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR))
        elif address==symbols['panel_ticks']:
            machine.reg_write(UC_ARM_REG_R0,data['ticks']&0xffffffff)
            machine.reg_write(UC_ARM_REG_R1,data['ticks']>>32)
            machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR))

    def read(machine,access,address,size,value,user):
        if address==0x0708140c:
            put(address,0x40 if case=='TWI_timeout' else 0x48)
        elif address==0x07081410:put(address,data['status'])
        elif address==0x07081408 and data['phase']=='read':
            put(address,data['pmic'].get(data['reg'],0))
        elif address==0x055090e0:put(address,0 if case=='PLL_timeout' else 1<<26)
        elif address in parents:
            value=get(address)
            failed=(address==0x02001020 and case=='periph_timeout') or (
                address==0x02001040 and case=='video_parent_timeout')
            if value&1<<31 and not failed:value|=1<<28
            else:value&=~(1<<28)
            put(address,value)
        elif address==0x05508010:
            put(address,1 if data['video'] or case=='LP_timeout' else 0)
        elif address==0x05508200:put(address,3)
        elif address==0x05508240:
            values={0xda:0x93,0xdb:0x65,0xdc:4,0x0a:0x18}
            if case=='panel_ID_mismatch':values[0xda]=0x94
            if case=='panel_not_awake':values[0x0a]=8
            put(address,0x21|(values.get(data['command'],0)<<8))
        elif address==0x055082e0:
            if data['video'] and case!='scan_stopped':data['line']+=87
            put(address,data['line'])

    def write(machine,access,address,size,value,user):
        assert size==4,(hex(address),size)
        # No DDR, eMMC, CPU PLL or PMIC-voltage MMIO is mapped or allowed.
        assert (0x02000000<=address<0x02002000 or address==0x0205000c or
            0x05500000<=address<0x0550a000 or 0x07081400<=address<0x07081420),hex(address)
        data['writes'].append((address,value))
        if address==0x07081408:data['tx']=value
        elif address==0x0708140c:
            if value==0x68:
                data['status']=0x10 if data['bus'] else 8
                data['bus']=True;data['phase']='address'
            elif value==0x58:
                data['bus']=False;data['phase']='address'
                # stop() polls STOP clear; model hardware's completion.
            elif value==0x48:
                if data['phase']=='address':
                    assert data['tx'] in (0x68,0x69)
                    data['status']=0x40 if data['tx']==0x69 else 0x18
                    data['phase']='read' if data['tx']==0x69 else 'register'
                elif data['phase']=='register':
                    data['reg']=data['tx'];data['status']=0x28;data['phase']='value'
                elif data['phase']=='value':
                    assert data['reg']==0x91 and data['tx'] in (0xd5,0xd7,0xdd,0xdf)
                    data['pmic_writes'].append(data['tx'])
                    if case!='rail_write_failure' or data['tx'] in (0xd5,0xd7):
                        data['pmic'][0x91]=data['tx']
                    data['status']=0x28
                elif data['phase']=='read':data['status']=0x58
        elif address==0x05508300:
            h=value&0xffffff
            masks=(0xf12cb7,0xf2555b,0x749a6d,0xb8e38e,0xdf03f0,0xeffc00)
            ecc=sum(((h&m).bit_count()&1)<<i for i,m in enumerate(masks))
            assert value>>24==ecc
            if h&255==6:data['command']=(h>>8)&255
        elif address==0x05508048:
            if value==6|(3<<24)|(7<<12)|(6<<28)|(15<<20):data['video']=True
        elif address==0x02000c80 and value&1:
            assert case in successes
            assert data['video'] and data['command']==0x0a and data['line']>=174
            data['backlight']=True

    uc.hook_add(UC_HOOK_CODE,code)
    for start,end in ((0x02000000,0x02005fff),(0x05500000,0x0550ffff),(0x07081000,0x07081fff)):
        uc.hook_add(UC_HOOK_MEM_READ,read,begin=start,end=end)
        uc.hook_add(UC_HOOK_MEM_WRITE,write,begin=start,end=end)
    uc.reg_write(UC_ARM_REG_CPSR,0x1d3)
    uc.reg_write(UC_ARM_REG_SP,0x2d000)
    uc.reg_write(UC_ARM_REG_LR,0x5f000)
    uc.reg_write(UC_ARM_REG_R0,1260)
    saved=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
           UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
    for i,reg in enumerate(saved):uc.reg_write(reg,0x54321000+i)
    uc.emu_start(0x44168,0x5f000,timeout=20_000_000,count=3_000_000)
    assert uc.reg_read(UC_ARM_REG_PC)==0x5f000,case
    assert uc.reg_read(UC_ARM_REG_SP)==0x2d000
    assert [uc.reg_read(reg) for reg in saved]==[0x54321000+i for i in range(8)]
    assert data['voltage_calls']==[1260]
    assert uc.reg_read(UC_ARM_REG_R0)==(0xffffffff if case=='voltage_failure' else 0)
    receipt=list(struct.unpack('<16I',uc.mem_read(0x2d200,64)))
    if case=='voltage_failure':assert not data['writes'] and receipt==[0]*16
    else:
        assert receipt[:2]==[0xa523ed01,2]
        if case in successes:
            assert receipt[2:4]==[0x100,1] and data['backlight']
            assert data['pmic'][0x91] in (0xdd,0xdf)
        else:
            assert receipt[2]&0xe0000000==0xe0000000 and receipt[3]==0 and not data['backlight']
            expected=0x15 if case=='PMIC_enable_unknown' else 0xd5
            assert data['pmic'][0x91]==expected,(case,data['pmic'])
            for address,value in initial.items():assert get(address)==value,(case,hex(address))
            for address,value in parents.items():assert get(address)==value,(case,hex(address))
    assert not [a for a,_ in data['writes'] if 0x02001000<=a<0x02001100 and a not in parents]
    results.append(dict(case=case,status='PASS',delay_calls=len(data['delays']),
        virtual_delay_us=sum(data['delays']),PMIC_enable_writes=data['pmic_writes'],
        backlight_only_after_ID_wake_and_changing_scan=data['backlight'],receipt=receipt))

manifest.update(ARM_emulation_verified=True,emulation=results,
    emulator_exercised_real_TWI_state_machine=True,
    emulator_has_no_DRAM_or_eMMC_or_CPU_PLL_mapping=True)
(folder/'loader.toc0.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
(root/'evidence/boot-panel-early-v2-emulation.json').write_text(json.dumps(dict(
    image_sha256=manifest['image_sha256'],tests=results),indent=2)+'\n',encoding='utf-8')
print('EARLY_PANEL_ACTUAL_ARM_TWI_GUARDS_ROLLBACK_AND_NO_DRAM_PASS',len(results),flush=True)
