"""Exercise exact ARM early-clock code against bounded PLL states and failures."""
import json
from pathlib import Path
import struct
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'build/host-unicorn'))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R4, UC_ARM_REG_R5,
    UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10,
    UC_ARM_REG_R11, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_CPSR)

folder = root/'build/boot-early-cpub'
binary = (folder/'loader.bin').read_bytes()
results = []
for case in ('normal', 'normal_div2', 'already_PLL', 'unknown_PLL', 'unknown_mux',
             'lock_timeout', 'CID_mismatch', 'emmc_failure'):
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0x20000, 0x40000)
    uc.mem_map(0x08817000, 0x1000)
    uc.mem_write(0x44000, binary)
    state = dict(pll=0x48801400, mux=0, delays=[], reads=0, writes=[], init_calls=0)
    if case == 'normal_div2': state['mux'] = 1 << 16
    if case == 'already_PLL': state.update(pll=0xc8801400, mux=3 << 24)
    if case == 'unknown_PLL': state['pll'] = 0x48801500
    if case == 'unknown_mux': state['mux'] = 1 << 24
    initial = (state['pll'], state['mux'])
    error = -9 if case == 'CID_mismatch' else -1 if case == 'emmc_failure' else 0

    def code(machine, address, size, user):
        if address == 0x44c7c:
            state['init_calls'] += 1
            machine.reg_write(UC_ARM_REG_R0, error & 0xffffffff)
            machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))
        elif address == 0x44134:
            state['delays'].append(machine.reg_read(UC_ARM_REG_R0))
            machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))
        elif address == 0x444a4:
            # Stop immediately after the actual patched BL returns to its caller.
            machine.emu_stop()

    def read(machine, access, address, size, value, user):
        assert size == 4 and address in (0x0881700c, 0x08817064)
        state['reads'] += 1
        machine.mem_write(address, struct.pack('<I', state['pll'] if address == 0x0881700c else state['mux']))

    def write(machine, access, address, size, value, user):
        assert size == 4 and address in (0x0881700c, 0x08817064)
        state['writes'].append((hex(address), hex(value)))
        if address == 0x0881700c:
            state['pll'] = value
            if value == 0xe4801400 and case != 'lock_timeout':
                state['pll'] |= 1 << 28
        else:
            state['mux'] = value

    uc.hook_add(UC_HOOK_CODE, code)
    uc.hook_add(UC_HOOK_MEM_READ, read, begin=0x08817000, end=0x08817fff)
    uc.hook_add(UC_HOOK_MEM_WRITE, write, begin=0x08817000, end=0x08817fff)
    uc.reg_write(UC_ARM_REG_CPSR, 0x1d3)
    uc.reg_write(UC_ARM_REG_SP, 0x2d000)
    uc.reg_write(UC_ARM_REG_LR, 0x5f000)
    saved = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
             UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)
    for i, reg in enumerate(saved): uc.reg_write(reg, 0x54321000+i)
    uc.emu_start(0x444a0, 0x5f000, timeout=10_000_000, count=100000)
    assert uc.reg_read(UC_ARM_REG_PC) == 0x444a4
    assert uc.reg_read(UC_ARM_REG_R0) == error & 0xffffffff
    assert uc.reg_read(UC_ARM_REG_SP) == 0x2d000
    assert [uc.reg_read(reg) for reg in saved] == [0x54321000+i for i in range(8)]
    assert state['init_calls'] == 1
    receipt = list(struct.unpack('<6I', uc.mem_read(0x2df40, 24)))
    if error:
        assert state['reads'] == 0 and state['writes'] == [] and receipt == [0]*6
    else:
        expected = 1 if case.startswith('normal') else 2 if case == 'already_PLL' else 4 if case == 'lock_timeout' else 3
        assert receipt[:4] == [0xa523cb01, expected, *initial]
        assert receipt[4:] == [state['pll'], state['mux']]
        if case.startswith('normal'):
            assert state['mux'] == 3 << 24 and len(state['writes']) == 3
            assert state['delays'] == [20, 20]
        elif case == 'lock_timeout':
            assert (state['pll'], state['mux']) == initial
            assert state['delays'] == [100]*1000 and len(state['writes']) == 2
        else:
            assert state['writes'] == [] and (state['pll'], state['mux']) == initial
    results.append(dict(case=case, result='PASS', register_writes=state['writes'],
                        delay_calls=len(state['delays']), receipt=[hex(v) for v in receipt]))

path = folder/'loader.toc0.json'
manifest = json.loads(path.read_text())
manifest.update(ARM_emulation_verified=True, emulation=results)
path.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8', newline='\n')
(root/'evidence/boot-early-cpub-emulation.json').write_text(json.dumps(dict(
    actual_patched_BL_executed=True, no_PMIC_mapped_or_written=True, tests=results,
    image_sha256=manifest['image_sha256']), indent=2)+'\n', encoding='utf-8')
print('EARLY_CPUB_ACTUAL_ARM_GUARDS_AND_RETURN_PATHS_PASS', json.dumps(results), flush=True)
