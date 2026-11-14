#!/usr/bin/env python3
"""Execute the actual ARM CID guard with an emulated eMMC init response."""
import argparse,struct,sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('toc0',type=Path);p.add_argument('--unicorn-path',type=Path)
    args=p.parse_args()
    if args.unicorn_path:sys.path.insert(0,str(args.unicorn_path))
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_R0
    firmware=args.toc0.read_bytes()[0xf80:]
    cases=(('original','3e01ff55454d20202010209170281b59',0),
           ('different-serial','3e01ff55454d2020ffeeddccbbaa0099',0),
           ('wrong-product','3e01ff4e4f5045202010209170281b59',-9))
    for name,cid,expected in cases:
        uc=Uc(UC_ARCH_ARM,UC_MODE_ARM);uc.mem_map(0x20000,0x40000)
        uc.mem_write(0x44000,firmware);uc.reg_write(UC_ARM_REG_SP,0x3e000)
        uc.reg_write(UC_ARM_REG_LR,0x21000)
        def hook(machine,address,size,user):
            if address==0x447d4:
                machine.mem_write(machine.reg_read(UC_ARM_REG_R0),bytes.fromhex(cid)[::-1])
                machine.reg_write(UC_ARM_REG_R0,0)
                machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR))
            elif address==0x21000:machine.emu_stop()
        uc.hook_add(UC_HOOK_CODE,hook)
        uc.emu_start(0x44c7c,0x21004,count=2000)
        actual=uc.reg_read(UC_ARM_REG_R0);actual=actual if actual<0x80000000 else actual-0x100000000
        assert actual==expected,(name,actual,expected)
        assert uc.reg_read(UC_ARM_REG_PC)==0x21000,'Guard did not return'
        print('ARM_CID_GUARD_PASS',name,actual)

if __name__=='__main__':main()
