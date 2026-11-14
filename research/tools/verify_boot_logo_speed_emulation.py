"""Execute the front-loaded ARM boost, real TWI/PLL guards and all exits."""
import json
import struct
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'build/host-unicorn'))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *

profile = sys.argv[1] if len(sys.argv) == 2 else 'boot-logo-speed'
assert profile in ('boot-logo-speed', 'boot-logo-overlap')
folder = root/'build'/profile
binary = (folder/'sram-loader.bin').read_bytes()
symbols = {items[2]: int(items[0], 16) for line in (folder/'speed.symbols.txt').read_text().splitlines()
           if len(items := line.split()) == 3}
registers = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4,
             UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9,
             UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_R12, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC]
cases = ('normal', 'DVM_bit_preserved', 'wrong_SID', 'unknown_PLL', 'unknown_mux',
         'wrong_PMIC_ID', 'unknown_voltage', 'TWI_timeout', 'raise_readback_failure',
         'PLL_update_timeout', 'PLL_lock_timeout', 'voltage_failure',
         'card_failure', 'DRAM_failure', 'common_failure_exit', 'restore_lock_failure', 'lower_readback_failure')
results = []
for case in cases:
    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for base, size in ((0x20000, 0x40000), (0x08817000, 0x1000), (0x07081000, 0x1000),
                       (0x03006000, 0x1000), (0x02050000, 0x1000), (0x07090000, 0x1000)):
        u.mem_map(base, size)
    u.mem_write(0x44000, binary)
    original_mv = 41 if case == 'unknown_voltage' else 0xa8
    data = dict(pll=0xf8801400, mux=0x03000305,
                pmic={3: 0x49 if case == 'wrong_PMIC_ID' else 0xff, 0x83: original_mv},
                bus=False, phase='address', status=0, tx=0, reg=0, writes=[], pmic_writes=[],
                ticks=2400000, card_calls=0, panel_calls=0, restoring=False, fatal=False)
    if case == 'unknown_PLL': data['pll'] = 0xf8801500
    if case == 'unknown_mux': data['mux'] = 0x02000305
    initial = (data['pll'], data['mux'])
    def put(address, value):
        u.mem_write(address, struct.pack('<I', value & 0xffffffff))
    def read(machine, access, address, size, value, user):
        assert size == 4
        if address == 0x08817004: put(address, data['pll'])
        elif address == 0x08817060: put(address, data['mux'])
        elif address == 0x03006248: put(address, 0x38 if case == 'wrong_SID' else 0x48)
        elif address == 0x0708140c: put(address, 0x40 if case == 'TWI_timeout' else 0x48)
        elif address == 0x07081410: put(address, data['status'])
        elif address == 0x07081408 and data['phase'] == 'read': put(address, data['pmic'].get(data['reg'], 0))
        else: raise AssertionError((case, 'unexpected MMIO read', hex(address)))
    def write(machine, access, address, size, value, user):
        assert size == 4
        data['writes'].append((address, value))
        if address == 0x08817004:
            n = (value >> 8) & 255
            if n == 59: assert data['pmic'][0x83] & 127 == 65, 'Frequency raised before voltage'
            data['pll'] = value
            if not (case == 'PLL_update_timeout' and n == 59): data['pll'] &= ~(1 << 26)
            locked = not ((case == 'PLL_lock_timeout' and n == 59) or
                          (case == 'restore_lock_failure' and data['restoring']))
            if locked and value & (1 << 29): data['pll'] |= 1 << 28
            else: data['pll'] &= ~(1 << 28)
        elif address == 0x08817060: data['mux'] = value
        elif address == 0x07081408: data['tx'] = value
        elif address == 0x0708140c:
            if value == 0x68:
                data['status'] = 0x10 if data['bus'] else 8
                data.update(bus=True, phase='address')
            elif value == 0x58: data.update(bus=False, phase='address')
            elif value == 0x48:
                if data['phase'] == 'address':
                    assert data['tx'] in (0x68, 0x69)
                    data['status'] = 0x40 if data['tx'] == 0x69 else 0x18
                    data['phase'] = 'read' if data['tx'] == 0x69 else 'register'
                elif data['phase'] == 'register':
                    data.update(reg=data['tx'], status=0x28, phase='value')
                elif data['phase'] == 'value':
                    assert data['reg'] == 0x83 and 40 <= data['tx'] & 127 <= 65
                    assert data['tx'] & 128 == original_mv & 128
                    if (data['tx'] & 127) < (data['pmic'][0x83] & 127):
                        assert (data['pll'] >> 8) & 255 == 20, 'Voltage lowered before clock'
                    data['pmic_writes'].append(data['tx'])
                    fail = ((case == 'raise_readback_failure' and not data['restoring'] and data['tx'] & 127 == 43) or
                            (case == 'lower_readback_failure' and data['restoring']))
                    if not fail: data['pmic'][0x83] = data['tx']
                    data['status'] = 0x28
                elif data['phase'] == 'read': data['status'] = 0x58
        else: raise AssertionError((case, 'unexpected MMIO write', hex(address)))
    def code(machine, address, size, user):
        if address == symbols['original_panel_voltage']:
            assert machine.reg_read(UC_ARM_REG_R0) == 1260 and data['card_calls'] == 0
            data['panel_calls'] += 1
            data['ticks'] += 1600000*24
            machine.reg_write(UC_ARM_REG_R0, 0xffffffff if case == 'voltage_failure' else 0)
            machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))
        elif address in (symbols.get('boot_panel_finish', -1), symbols.get('boot_panel_cancel', -1)):
            machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))
        elif address == 0x4c700:
            data['card_calls'] += 1
            machine.reg_write(UC_ARM_REG_R0, 0xfffffff7 if case == 'card_failure' else 0)
            machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))
        elif address == 0x44134:
            data['ticks'] += machine.reg_read(UC_ARM_REG_R0)*24
            machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))
        elif address in (0x4403c, 0x5f000): machine.emu_stop()
        elif address == 0x4e5e0: data['restoring'] = True
        elif address == 0x4e200:
            data['fatal'] = True
            machine.emu_stop()
        else:
            instruction = struct.unpack('<I', machine.mem_read(address, 4))[0]
            if instruction & 0xfff00fff == 0xec500f0e:
                machine.reg_write(registers[(instruction >> 12) & 15], data['ticks'] & 0xffffffff)
                machine.reg_write(registers[(instruction >> 16) & 15], data['ticks'] >> 32)
                machine.reg_write(UC_ARM_REG_PC, address+4)
    u.hook_add(UC_HOOK_CODE, code)
    for start, end in ((0x08817000, 0x08817fff), (0x07081000, 0x07081fff), (0x03006000, 0x03006fff)):
        u.hook_add(UC_HOOK_MEM_READ, read, begin=start, end=end)
        u.hook_add(UC_HOOK_MEM_WRITE, write, begin=start, end=end)
    u.reg_write(UC_ARM_REG_CPSR, 0x1d3)
    u.reg_write(UC_ARM_REG_SP, 0x2d000)
    u.reg_write(UC_ARM_REG_LR, 0x5f000)
    u.reg_write(UC_ARM_REG_R0, 1260)
    saved = registers[4:12]
    for index, register in enumerate(saved): u.reg_write(register, 0x54321000+index)
    u.emu_start(0x44168, 0x60000, timeout=20_000_000, count=2_000_000)
    assert u.reg_read(UC_ARM_REG_PC) == 0x5f000 and u.reg_read(UC_ARM_REG_SP) == 0x2d000
    assert [u.reg_read(register) for register in saved] == [0x54321000+i for i in range(8)]
    assert u.reg_read(UC_ARM_REG_R0) == (0xffffffff if case == 'voltage_failure' else 0)
    assert data['card_calls'] == 0 and data['panel_calls'] == 1
    receipt = lambda: list(struct.unpack('<16I', u.mem_read(0x2d500, 64)))
    successful = case in ('normal', 'DVM_bit_preserved', 'card_failure', 'DRAM_failure',
                         'common_failure_exit', 'restore_lock_failure', 'lower_readback_failure')
    if successful:
        assert receipt()[2:4] == [2, 1] and receipt()[8:10] == [1416000, 1150]
        assert (data['pll'] >> 8) & 255 == 59 and data['pmic'][0x83] & 127 == 65
    elif case in ('PLL_update_timeout', 'PLL_lock_timeout', 'raise_readback_failure'):
        assert receipt()[2:4] == [4, 0] and data['pmic'][0x83] == original_mv
    else:
        assert not data['pmic_writes'] and (data['pll'], data['mux']) == initial
    if case not in ('voltage_failure', 'DRAM_failure'):
        u.reg_write(UC_ARM_REG_LR, 0x5f000)
        u.emu_start(symbols['boot_logo_speed_card_init'], 0x60000, timeout=20_000_000, count=2_000_000)
        assert u.reg_read(UC_ARM_REG_PC) == 0x5f000 and data['card_calls'] == 1
        assert u.reg_read(UC_ARM_REG_R0) == (0xfffffff7 if case == 'card_failure' else 0)
        assert u.reg_read(UC_ARM_REG_SP) == 0x2d000
    if case in ('voltage_failure', 'DRAM_failure'):
        frame = [0x11110000+i for i in range(5)]+[0x5f000]
        u.mem_write(0x2c000, struct.pack('<6I', *frame))
        u.reg_write(UC_ARM_REG_SP, 0x2c000)
        u.reg_write(UC_ARM_REG_R0, 0xdeadbeef)
        u.emu_start(0x4441c, 0x60000, timeout=20_000_000, count=2_000_000)
        assert u.reg_read(UC_ARM_REG_PC) == 0x5f000 and u.reg_read(UC_ARM_REG_SP) == 0x2c018
        assert u.reg_read(UC_ARM_REG_R0) == 0xdeadbeef
        assert [u.reg_read(register) for register in saved[:5]] == frame[:5]
    elif case in ('common_failure_exit', 'card_failure'):
        frame = [0x11110000+i for i in range(8)]+[0x5f000]
        u.mem_write(0x2c000, struct.pack('<9I', *frame))
        u.reg_write(UC_ARM_REG_SP, 0x2c000)
        u.reg_write(UC_ARM_REG_R0, 0xdeadbeef)
        u.emu_start(0x445cc, 0x60000, timeout=20_000_000, count=2_000_000)
        assert u.reg_read(UC_ARM_REG_PC) == 0x5f000 and u.reg_read(UC_ARM_REG_SP) == 0x2c024
        assert u.reg_read(UC_ARM_REG_R0) == 0xdeadbeef
    else:
        u.reg_write(UC_ARM_REG_R0, 0x54000)
        u.reg_write(UC_ARM_REG_LR, 0x5f000)
        u.emu_start(0x4466c, 0x60000, timeout=20_000_000, count=2_000_000)
        if case in ('restore_lock_failure', 'lower_readback_failure'): assert data['fatal']
        else: assert u.reg_read(UC_ARM_REG_PC) == 0x4403c and u.reg_read(UC_ARM_REG_R0) == 0x54000
    if successful and not data['fatal']:
        assert receipt()[2:4] == [4, 0] and receipt()[12] == original_mv
        assert (data['pll'] >> 8) & 255 == 20 and data['mux'] == initial[1] and data['pmic'][0x83] == original_mv
    results.append(dict(case=case, status='PASS', CPU_receipt=receipt(), card_calls=data['card_calls'],
                        fatal_instead_of_unsafe_handoff=data['fatal']))
    print('EARLY_CPU_REAL_ARM_GUARD_AND_EXIT_PASS', case, flush=True)
manifest = json.loads((folder/'loader.toc0.json').read_text())
manifest.update(ARM_emulation_verified=True, speed_emulation=results,
                actual_original_TWI_PLL_guards_and_restore_executed=True)
(folder/'loader.toc0.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
(root/'evidence'/(profile+'-emulation.json')).write_text(json.dumps(results, indent=2)+'\n', encoding='utf-8')
print('EARLY_CPU_BOOST_ALL_ARM_PATHS_PASS', len(results), flush=True)
