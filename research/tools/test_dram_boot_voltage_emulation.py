"""Execute the exact patched ARM hook against a TWI/PMIC hardware model."""
import json
from pathlib import Path
import struct
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'build/host-unicorn'))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_CPSR

folder = root/'build/dram-boot-voltage'
binary = (folder/'loader.bin').read_bytes()
results = []
for case in ('normal', 'already_1260', 'wrong_request', 'wrong_pmic', 'nack', 'flag_timeout', 'reset_timeout'):
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0x20000, 0x40000)
    for address in (0x07010000, 0x07022000, 0x07081000): uc.mem_map(address, 0x1000)
    uc.mem_write(0x44000, binary)
    state = {'ctl': 0x40, 'status': 0xf8, 'data': 0, 'active': False, 'phase': 'idle',
             'address': 0, 'register': 0, 'writes': [], 'delays': 0,
             'gpio': {0x0701019c: 0x55002020, 0x07022000: 0xaabbccdd, 0x07022024: 0x98765432}}
    registers = {(0x34, 0x80): 0x0f, (0x34, 0x83): 0xa8, (0x34, 0x84): 0xa8,
                 (0x34, 0x85): 0xc9 if case == 'already_1260' else 0xbc,
                 (0x34, 0x86): 0, (0x34, 0x98): 0x0d,
                 (0x36, 3): 0 if case == 'wrong_pmic' else 0x49}
    original_gpio = state['gpio'].copy()

    def code(machine, address, size, _):
        if address in (0x44134, 0x44170):
            if address == 0x44134: state['delays'] += 1
            machine.reg_write(UC_ARM_REG_R0, 0)
            machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))

    def read(machine, access, address, size, value, _):
        assert size == 4
        if address in state['gpio']: value = state['gpio'][address]
        elif address == 0x0708140c: value = 0x40 if case == 'flag_timeout' else state['ctl']
        elif address == 0x07081410: value = state['status']
        elif address == 0x07081408: value = state['data']
        elif address == 0x07081418: value = int(case == 'reset_timeout')
        else: raise AssertionError(('unexpected MMIO read', hex(address)))
        machine.mem_write(address, struct.pack('<I', value))

    def write(machine, access, address, size, value, _):
        assert size == 4
        if address in state['gpio']:
            state['gpio'][address] = value
        elif address == 0x07081408:
            state['data'] = value
        elif address == 0x0708140c:
            state['ctl'] = 0x48
            if value & 0x10:
                state.update(active=False, phase='idle', status=0xf8, ctl=0x40)
            elif value & 0x20:
                state.update(status=0x10 if state['active'] else 8, active=True, phase='address')
            elif value & 8:
                if state['phase'] == 'address':
                    byte = state['data']
                    state['address'] = byte >> 1
                    if case == 'nack': state['status'] = 0x20
                    else:
                        assert state['address'] in (0x34, 0x36)
                        state['status'] = 0x40 if byte & 1 else 0x18
                        state['phase'] = 'receive' if byte & 1 else 'register'
                elif state['phase'] == 'register':
                    state.update(register=state['data'], phase='write', status=0x28)
                elif state['phase'] == 'write':
                    assert state['address'] == 0x34 and state['register'] == 0x85
                    assert 0xbc <= state['data'] <= 0xc9
                    registers[(0x34, 0x85)] = state['data']
                    state['writes'].append(state['data'])
                    state['status'] = 0x28
                elif state['phase'] == 'receive':
                    state.update(data=registers[(state['address'], state['register'])], status=0x58)
                else: raise AssertionError(('unknown transfer phase', state['phase']))
        elif address in (0x07081414, 0x07081418, 0x0708141c): pass
        else: raise AssertionError(('unexpected MMIO write', hex(address), value))

    uc.hook_add(UC_HOOK_CODE, code)
    for start, end in ((0x07010000, 0x07010fff), (0x07022000, 0x07022fff), (0x07081000, 0x07081fff)):
        uc.hook_add(UC_HOOK_MEM_READ, read, begin=start, end=end)
        uc.hook_add(UC_HOOK_MEM_WRITE, write, begin=start, end=end)
    uc.reg_write(UC_ARM_REG_CPSR, 0x1d3)
    uc.reg_write(UC_ARM_REG_SP, 0x2d000)
    uc.reg_write(UC_ARM_REG_LR, 0x5f000)
    uc.reg_write(UC_ARM_REG_R0, 1200 if case == 'wrong_request' else 1260)
    uc.emu_start(0x44168, 0x5f000, timeout=10_000_000, count=300000)
    assert uc.reg_read(UC_ARM_REG_PC) == 0x5f000, case
    receipt = struct.unpack('<5I', bytes(uc.mem_read(0x2e080, 20)))
    success = case in ('normal', 'already_1260')
    assert uc.reg_read(UC_ARM_REG_R0) == (0 if success else 0xffffffff), case
    if success:
        assert receipt[0:2] == (0xa523dc03, 1260) and receipt[3:] == (0xc9, 2)
        assert state['writes'] == (list(range(0xbd, 0xca)) if case == 'normal' else [])
    else:
        assert not state['writes'], case
        assert receipt[4] == (1 if case == 'wrong_request' else 0xee), receipt
    if case != 'wrong_request':
        assert state['gpio'][0x0701019c] == original_gpio[0x0701019c] | 0x10001
        assert state['gpio'][0x07022000] & ~0xff == original_gpio[0x07022000] & ~0xff
        assert state['gpio'][0x07022024] & ~0xf == original_gpio[0x07022024] & ~0xf
    results.append({'case': case, 'result': 'PASS', 'PMIC_register_0x85_writes': state['writes'],
                    'delay_calls': state['delays'], 'receipt': [hex(x) for x in receipt]})
record = {'actual_ARM_binary_executed': True, 'entry': 'original patched hook 0x44168',
          'DRAM_mapped_in_emulator': False, 'tests': results}
(folder/'EMULATION.json').write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps(record, indent=2))
