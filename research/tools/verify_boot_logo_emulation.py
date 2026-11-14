"""Run the real ARM optional loader/decoder/DE sequence and its failure paths."""
import hashlib,json,struct,sys,zlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'build/host-unicorn'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
out=root/'build/boot-logo';binary=(out/'sram-loader.bin').read_bytes();payload=(out/'payload.bin').read_bytes()
m=json.loads((out/'loader.toc0.json').read_text());results=[]
symbols={p[2]:int(p[0],16) for s in (out/'logo.symbols.txt').read_text().splitlines() if len(p:=s.split())==3}
registers=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,
    UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC]
cases=('normal','CRC_failure','read_failure','init_failure','MMU_active','panel_failed','DE_domain_off',
       'DE_busy','DE_version_mismatch','line_timeout','RCQ_timeout','DSI_pause_timeout','DSI_HSC_timeout',
       'RLE_overflow','RLE_zero_run','RLE_short_output')
# Execute the changed pre-DRAM MOV in isolation: fixed black, no color bytes.
black=next(p for p in m['patches'] if p['old']==0xe3a030ff)
probe=Uc(UC_ARCH_ARM,UC_MODE_ARM);probe.mem_map(0x44000,0xc000);probe.mem_write(0x44000,binary)
probe.reg_write(UC_ARM_REG_CPSR,0x1d3);probe.emu_start(black['address'],black['address']+4,count=1)
assert probe.reg_read(UC_ARM_REG_R3)==0x10000000
for case in cases:
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for base,size in ((0x20000,0x40000),(0x42000000,0x900000),(0x02000000,0x6000),
                      (0x05000000,0x400000),(0x05500000,0x10000),(0x07065000,0x1000)):
        u.mem_map(base,size)
    u.mem_write(0x44000,binary)
    def put(a,v):u.mem_write(a,struct.pack('<I',v&0xffffffff))
    def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
    data=dict(ticks=168000000,reads=0,writes=[],jump=0x00650001,stream=True,engine=False)
    put(0x2d200,0xa523ed01);put(0x2d20c,0 if case=='panel_failed' else 1)
    put(0x07065008,0 if case=='DE_domain_off' else 8)
    put(0x0200160c,1 if case=='DE_busy' else 0)
    put(0x05502040,0x81000021);put(0x05508010,1);put(0x05508048,0x63f07006)
    put(0x0550804c,data['jump']);put(0x055082f8,0x10000000)
    put(0x05008014,0 if case=='DE_version_mismatch' else 0x03500200)
    def code(machine,a,size,user):
        if a==0x4e6a4:
            machine.reg_write(UC_ARM_REG_R0,0xffffffff if case=='init_failure' else 0)
            machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR))
        elif a==0x44bac:
            sector=machine.reg_read(UC_ARM_REG_R0)-49152;dest=machine.reg_read(UC_ARM_REG_R1)
            assert 0<=sector<len(payload)//512 and dest==0x30200
            chunk=payload[sector*512:(sector+1)*512]
            if case=='CRC_failure' and sector==len(payload)//512-1:chunk=bytes([chunk[0]^1])+chunk[1:]
            machine.mem_write(dest,chunk);data['reads']+=1
            machine.reg_write(UC_ARM_REG_R0,0xffffffff if case=='read_failure' and sector==1 else 0)
            machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR))
        elif a==0x4ce00:
            crc=machine.reg_read(UC_ARM_REG_R0);addr=machine.reg_read(UC_ARM_REG_R1)
            machine.reg_write(UC_ARM_REG_R0,zlib.crc32(machine.mem_read(addr,512),crc^0xffffffff)^0xffffffff)
            machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR))
        elif a==0x44134:
            data['ticks']+=24*machine.reg_read(UC_ARM_REG_R0)
            machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR))
        elif a==m['payload_entry'] and case.startswith('RLE_'):
            if case=='RLE_overflow':put(0x42002000,0x80100001)
            elif case=='RLE_zero_run':put(0x42002000,0x80000000)
            else:
                rle=(out/'splash.rle').read_bytes();pos=0;last=0
                while pos<len(rle):
                    last=pos;token=struct.unpack_from('<I',rle,pos)[0]
                    pos+=8 if token&0x80000000 else 4+4*token
                token=struct.unpack_from('<I',rle,last)[0];assert token&0x80000000 and token&0x7fffffff>1
                put(0x42002000+last,token-1)
        elif a==0x444a4:machine.emu_stop()
        else:
            instruction=get(a)
            if instruction&0xfff00fff==0xec500f0e:
                data['ticks']+=24
                machine.reg_write(registers[(instruction>>12)&15],data['ticks']&0xffffffff)
                machine.reg_write(registers[(instruction>>16)&15],data['ticks']>>32)
                machine.reg_write(UC_ARM_REG_PC,a+4)
            elif instruction&0x0fff0fff==0x0e110f10:
                machine.reg_write(registers[(instruction>>12)&15],1 if case=='MMU_active' else 0)
                machine.reg_write(UC_ARM_REG_PC,a+4)
            elif instruction&0x0fff0fff in (0x0e070f15,0x0e070fd5):machine.reg_write(UC_ARM_REG_PC,a+4)
    def read(machine,access,a,size,value,user):
        if a==0x055020fc:put(a,0 if case=='line_timeout' else 200<<16)
        elif a==0x05008104:put(a,0x1c if data['engine'] else 0)
        elif a==0x05508010:put(a,1 if data['stream'] else 0)
        elif a==0x055082e0:put(a,(data['ticks']//240)%1300)
    def write(machine,access,a,size,value,user):
        assert size==4,(case,hex(a),size)
        data['writes'].append((a,value))
        if a==0x05008110 and value==1:
            if case!='RCQ_timeout':
                put(0x05008104,0x1c)
                put(0x05008104,0x1c)
                # The RCQ must include the actual, reserved framebuffer.
                heads=machine.mem_read(0x42800000,14*16)
                for addr,length,dirty,offset in struct.iter_unpack('<4I',heads):
                    assert dirty==1 and 0x42800200<=addr<0x42801000 and length<=0x88
                    machine.mem_write(0x05000000+offset,bytes(machine.mem_read(addr,length)))
                data['engine']=True
        if a==0x0550804c and value&(1<<28):data['stream']=case=='DSI_pause_timeout'
        if a==0x05508010:
            data['stream']=bool(value&1) and get(0x05508048)!=0xf02
            if case=='DSI_HSC_timeout' and get(0x05508048)==0xf02:data['stream']=True
        if a==0x055082f8 and value==255:
            assert data['engine'] and get(0x051c1010)==0x42400000
            assert bytes(machine.mem_read(0x42400000,4096000))==(out/'splash-native.bgra').read_bytes()
    u.hook_add(UC_HOOK_CODE,code)
    for start,end in ((0x02000000,0x02005fff),(0x05000000,0x053fffff),(0x05500000,0x0550ffff),(0x07065000,0x07065fff)):
        u.hook_add(UC_HOOK_MEM_READ,read,begin=start,end=end)
        u.hook_add(UC_HOOK_MEM_WRITE,write,begin=start,end=end)
    u.reg_write(UC_ARM_REG_CPSR,0x1d3);u.reg_write(UC_ARM_REG_SP,0x2d000)
    for i,reg in enumerate(registers[4:12]):u.reg_write(reg,0x12340000+i)
    u.emu_start(0x444a0,0x60000,timeout=60_000_000,count=30_000_000)
    assert u.reg_read(UC_ARM_REG_PC)==0x444a4,(case,hex(u.reg_read(UC_ARM_REG_PC)))
    assert u.reg_read(UC_ARM_REG_SP)==0x2d000
    assert [u.reg_read(r) for r in registers[4:12]]==[0x12340000+i for i in range(8)]
    receipt=struct.unpack('<8I3Q12I',u.mem_read(0x2d600,104))
    if case=='normal':
        assert receipt[2:5]==(0x100,1,0),receipt
        assert hashlib.sha256(u.mem_read(0x42400000,4096000)).hexdigest()==m['native_bgra_sha256']
    else:
        assert receipt[3]==0 and receipt[4]>0,(case,receipt)
        assert get(0x055082f8)==0x10000000
    assert u.reg_read(UC_ARM_REG_R0)==(0xffffffff if case=='init_failure' else 0)
    assert all(a in (0x02000c80,0x02001600,0x0200160c) or 0x05000000<=a<0x05600000 for a,_ in data['writes'])
    results.append(dict(case=case,status='PASS',receipt=list(receipt),reads=data['reads']))
    print('ARM_CASE_PASS',case,flush=True)
m.update(ARM_emulation_verified=True,emulation=results)
(out/'loader.toc0.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
(root/'evidence/boot-logo-emulation.json').write_text(json.dumps(results,indent=2)+'\n')
print('BOOT_LOGO_REAL_ARM_PIXEL_EXACT_AND_FAILURE_PATHS_PASS',len(results),flush=True)
