"""Execute the complete ARM64 entry with the real production compressed kernel.

Only EL2/cache/counter system registers are modeled. All alias, relocation,
decoder, header, CRC and Linux handoff instructions execute in Unicorn.
"""
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'build/host-unicorn'))
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X0, UC_ARM64_REG_PSTATE
import unicorn.arm64_const as regs

out=root/'build/boot-compact'
entry=(out/'linux-entry.bin').read_bytes()
kernel=(out/'kernel.lz4-block').read_bytes()
raw=(out/'Image').read_bytes()
instructions={}
for line in (out/'linux-entry.disassembly').read_text().splitlines():
    found=re.match(r'\s*([0-9a-f]+):\s+[0-9a-f]+\s+(.*)',line)
    if found:instructions[int(found[1],16)]=found[2].strip()

def run(case, data):
    uc=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
    for address,size in ((0x2d000,4096),(0x07090000,4096),(0x02050000,4096),
                         (0x47000000,4096),(0x48000000,0x4000000),(0x50000000,0x800000)):
        uc.mem_map(address,size)
    for address in range(0x41000000,0x140000000,0x10000000):uc.mem_map(address,4096)
    uc.mem_write(0x4a000000,entry);uc.mem_write(0x48080000,data)
    uc.reg_write(UC_ARM64_REG_PSTATE,0x3c9)
    record={};counter=1000000;system={'sctlr_el2':0,'tcr_el2':0,'mair_el2':0,'ttbr0_el2':0}
    def modeled(cpu,address,size,user):
        nonlocal counter
        op=instructions[address]
        if op.startswith('mrs'):
            dest,name=[item.strip() for item in op[3:].split(',')]
            values={**system,'cntfrq_el0':24000000,'id_aa64isar0_el1':1<<16,
                    'hcr_el2':0,'ctr_el0':4<<16,'esr_el2':0,'elr_el2':0,'cntpct_el0':counter}
            assert name in values,name
            cpu.reg_write(getattr(regs,'UC_ARM64_REG_'+dest.upper()),values[name]);counter+=24000
        elif op.startswith('msr'):
            name,value=[item.strip() for item in op[3:].split(',')]
            if name in system:system[name]=cpu.reg_read(getattr(regs,'UC_ARM64_REG_'+value.upper()))
        cpu.reg_write(UC_ARM64_REG_PC,address+4)
    for address,op in instructions.items():
        if op.startswith(('mrs','msr','ic\t','ic ','dc\t','dc ','tlbi')):
            uc.hook_add(UC_HOOK_CODE,modeled,begin=address,end=address)
    def handed(cpu,address,size,user):
        record['linux']=[cpu.reg_read(getattr(regs,'UC_ARM64_REG_X'+str(i))) for i in range(5)]
        cpu.emu_stop()
    uc.hook_add(UC_HOOK_CODE,handed,begin=0x48000000,end=0x48000000)
    def reset(cpu,access,address,size,value,user):
        record['reset']=value;cpu.emu_stop()
    uc.hook_add(UC_HOOK_MEM_WRITE,reset,begin=0x02050008,end=0x0205000b)
    uc.emu_start(0x4a000000,0,count=250000000)
    receipt=bytes(uc.mem_read(0x2d800,80))
    header=list(struct.unpack_from('<3Ii4I',receipt))
    if case=='production':
        assert record.get('linux')==[0x47000000,0,0,0,0x48000000],record
        assert bytes(uc.mem_read(0x48000000,len(raw)))==raw
        assert header[:4]==[0xa523c701,1,4,0],header
        assert struct.unpack('<I',uc.mem_read(0x07090114,4))[0]==16
        assert list(system.values())==[0,0,0,0],system
        assert struct.unpack('<I',receipt[68:72])[0]==3
        assert struct.unpack('<2Q',uc.mem_read(0x4bf00000,16))==((1<<54)|0x401,0x40000705)
    else:
        assert record.get('reset')==0x16aa0001 and 'linux' not in record,record
        assert header[3]!=0,header
        assert bytes(uc.mem_read(0x07090118,4))==struct.pack('<I',0xa52322ee)
    return dict(case=case,status='PASS',receipt=header,**record)

results=[run('production',kernel)]
bad=bytearray(kernel);bad[0]^=1;results.append(run('bad-header',bytes(bad)))
bad=bytearray(kernel);bad[-1]^=1;results.append(run('bad-output-CRC',bytes(bad)))
(out/'entry-emulation.json').write_text(json.dumps(dict(status='PASS',cases=results,
    entry_sha256=hashlib.sha256(entry).hexdigest(),decoded_kernel_sha256=hashlib.sha256(raw).hexdigest(),
    modeled='EL2 registers, cache maintenance and counter; translations/cache effects require actual hardware qualification'),indent=2)+'\n')
print('FULL_ARM64_COMPACT_ENTRY_EMULATION_PASS',json.dumps(results))
