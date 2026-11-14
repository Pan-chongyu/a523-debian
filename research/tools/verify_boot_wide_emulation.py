"""Execute the exact ARM width trial, sector comparisons and reset fallback."""
import hashlib
import json
from pathlib import Path
import struct
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'build/host-unicorn'))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8,
    UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_SP, UC_ARM_REG_LR,
    UC_ARM_REG_PC, UC_ARM_REG_CPSR)

folder = root/'build/boot-wide-emmc'
binary = (folder/'loader.bin').read_bytes()
cases = ('normal', 'CID_failure', 'unknown_clock', 'unknown_width', 'baseline_read_error',
         'CMD6_error', 'busy_timeout', 'CMD13_error', 'switch_error', 'wide_read_error',
         'corrupt_sector_0', 'corrupt_sector_1', 'corrupt_sector_2')
results = []
for case in cases:
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0x20000, 0x40000)
    uc.mem_map(0x04022000, 0x1000)
    uc.mem_map(0x02001000, 0x1000)
    uc.mem_write(0x44000, binary)
    state = dict(width=0, clock=0x10000, init_calls=0, commands=[], reads=[], writes=[], delays=0)
    if case == 'unknown_clock': state['clock'] = 0x1001d
    if case == 'unknown_width': state['width'] = 1

    def ret(machine, value=0):
        machine.reg_write(UC_ARM_REG_R0, value & 0xffffffff)
        machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))

    def code(machine, address, size, user):
        if address == 0x4c300:
            state['init_calls'] += 1
            if case != 'unknown_width': state['width'] = 0
            ret(machine, -9 if case == 'CID_failure' else 0)
        elif address == 0x44134:
            state['delays'] += 1
            ret(machine)
        elif address == 0x446cc:
            ci, arg, flags, response = [machine.reg_read(reg) for reg in
                (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
            assert (ci, arg, flags) in ((6, 0x03b70200, 0x140), (13, 0x10000, 0x140))
            state['commands'].append(ci)
            if response:
                machine.mem_write(response, struct.pack('<I', 0x80 if case == 'switch_error' else 0))
            ret(machine, -1 if (case == 'CMD6_error' and ci == 6) or (case == 'CMD13_error' and ci == 13) else 0)
        elif address == 0x44bac:
            lba = machine.reg_read(UC_ARM_REG_R0)
            dest = machine.reg_read(UC_ARM_REG_R1)
            assert lba in (4096, 98305, 100353)
            wide = state['width'] == 2
            state['reads'].append((lba, wide))
            payload = b''.join(hashlib.sha256(struct.pack('<II', lba, i)).digest() for i in range(16))
            if wide and case == 'corrupt_sector_%d' % ((4096, 98305, 100353).index(lba)):
                payload = bytes([payload[0]^1])+payload[1:]
            machine.mem_write(dest, payload)
            ret(machine, -1 if case == 'baseline_read_error' and not wide or case == 'wide_read_error' and wide else 0)
        elif address == 0x444a4:
            machine.emu_stop()

    def read(machine, access, address, size, value, user):
        assert size == 4
        values = {0x0402200c:state['width'], 0x04022004:state['clock'],
                  0x0402203c:0x200 if case == 'busy_timeout' else 0,
                  0x02001838:0x80000000}
        assert address in values
        machine.mem_write(address, struct.pack('<I', values[address]))

    def write(machine, access, address, size, value, user):
        assert address == 0x0402200c and size == 4 and value == 2
        state['writes'].append((hex(address), value))
        state['width'] = value

    uc.hook_add(UC_HOOK_CODE, code)
    for first, last in ((0x04022000, 0x04022fff), (0x02001000, 0x02001fff)):
        uc.hook_add(UC_HOOK_MEM_READ, read, begin=first, end=last)
        uc.hook_add(UC_HOOK_MEM_WRITE, write, begin=first, end=last)
    uc.reg_write(UC_ARM_REG_CPSR, 0x1d3)
    uc.reg_write(UC_ARM_REG_SP, 0x2d000)
    uc.reg_write(UC_ARM_REG_LR, 0x5f000)
    saved = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
             UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)
    for i, reg in enumerate(saved): uc.reg_write(reg, 0x54321000+i)
    uc.emu_start(0x444a0, 0x5f000, timeout=10_000_000, count=150000)
    assert uc.reg_read(UC_ARM_REG_PC) == 0x444a4
    assert uc.reg_read(UC_ARM_REG_SP) == 0x2d000
    assert [uc.reg_read(reg) for reg in saved] == [0x54321000+i for i in range(8)]
    error = -9 if case == 'CID_failure' else -1 if case == 'baseline_read_error' else 0
    assert uc.reg_read(UC_ARM_REG_R0) == error & 0xffffffff
    receipt = list(struct.unpack('<8I', uc.mem_read(0x2df80, 32)))
    expected = 0 if case == 'CID_failure' else 1 if case == 'normal' else 3 if case.startswith('unknown') else 5 if case == 'baseline_read_error' else 4
    assert receipt[1] == expected
    if case == 'normal':
        assert state['commands'] == [6, 13] and len(state['reads']) == 6
        assert receipt[4:7] == [3, 2, 0] and state['width'] == 2
    elif expected == 4:
        assert state['init_calls'] == 2 and state['width'] == 0
    else:
        assert not state['writes'] and not state['commands']
    results.append(dict(case=case, result='PASS', init_calls=state['init_calls'],
        volatile_bus_commands=state['commands'], register_writes=state['writes'],
        sector_reads=len(state['reads']), receipt=[hex(v) for v in receipt]))

path = folder/'loader.toc0.json'
manifest = json.loads(path.read_text())
manifest.update(ARM_emulation_verified=True, emulation=results)
path.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8', newline='\n')
(root/'evidence/boot-wide-emulation.json').write_text(json.dumps(dict(
    actual_patched_BL_executed=True, no_storage_data_clock_PMIC_write=True,
    tests=results, image_sha256=manifest['image_sha256']), indent=2)+'\n', encoding='utf-8')
print('BOOT_WIDE_ACTUAL_ARM_COMPARISON_AND_RESET_FALLBACK_PASS', json.dumps(results), flush=True)
