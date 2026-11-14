"""Reuse the real DSI/TWI failure harness for split rail/finish transactions."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = (root/'tools/verify_boot_panel_emulation.py').read_text(encoding='utf-8')
source = source.replace("folder=root/'build/boot-panel-early-v2'", "folder=root/'build/boot-logo-overlap'")
source = source.replace("'loader.bin'", "'sram-loader.bin'").replace("'panel-hook.symbols.txt'", "'panel.symbols.txt'")
source = source.replace("'unexpected_live_periph')", "'unexpected_live_periph','short_settle','cancel_before_training')")
source = source.replace("successes=('normal','original_CLDO2_enabled','periph_pre_enabled')",
                        "successes=('normal','original_CLDO2_enabled','periph_pre_enabled','short_settle')")
needle = "    uc.emu_start(0x44168,0x5f000,timeout=20_000_000,count=3_000_000)"
replacement = '''    uc.emu_start(symbols['boot_panel_voltage_entry'],0x5f000,timeout=20_000_000,count=3_000_000)
    early_result=uc.reg_read(UC_ARM_REG_R0)
    assert not data['backlight'] and not data['video']
    early_receipt=list(struct.unpack('<16I',uc.mem_read(0x2d200,64)))
    if early_receipt[2]==2:
        assert data['pmic'][0x91] in (0xdd,0xdf)
    finish_at=data['ticks']+(0 if case=='short_settle' else 3*24000000)
    data['ticks']=finish_at
    if case=='cancel_before_training':
        uc.reg_write(UC_ARM_REG_LR,0x5f000)
        uc.emu_start(symbols['boot_panel_cancel'],0x5f000,timeout=20_000_000,count=3_000_000)
        assert data['pmic'][0x91]==0xd5 and not data['backlight']
        assert not data['video']
        results.append(dict(case=case,status='PASS',pending_rail_restored_without_display=True))
        continue
    uc.reg_write(UC_ARM_REG_LR,0x5f000)
    uc.emu_start(symbols['boot_panel_finish'],0x5f000,timeout=20_000_000,count=3_000_000)
    uc.reg_write(UC_ARM_REG_R0,early_result)
    if case in successes:
        assert get(0x055082f8)==1<<28, 'No colorbars before verified image'
        if case=='short_settle': assert sum(data['delays'])>=1600000
        else: assert sum(data['delays'])<700000
'''
assert source.count(needle) == 1
source = source.replace(needle, replacement)
source = source.replace('ARM_emulation_verified=True,emulation=results,', 'panel_overlap_emulation_verified=True,panel_emulation=results,')
source = source.replace("'boot-panel-early-v2-emulation.json'", "'boot-logo-overlap-panel-emulation.json'")
source = source.replace("'EARLY_PANEL_ACTUAL_ARM_TWI_GUARDS_ROLLBACK_AND_NO_DRAM_PASS'", "'OVERLAPPED_PANEL_MINIMUM_SETTLE_AND_ALL_FAILURES_PASS'")
exec(compile(source, str(root/'tools/verify_boot_panel_emulation.py'), 'exec'), {'__file__': str(root/'tools/verify_boot_panel_emulation.py')})
