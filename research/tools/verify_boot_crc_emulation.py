"""Run both exact ARM CRC implementations and enforce their calling contract."""
import hashlib
import json
from pathlib import Path
import random
import struct
import sys
import zlib

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'build/host-unicorn'))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R4,
    UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9,
    UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
    UC_ARM_REG_CPSR)

folder = root / 'build/boot-latency-loader'
rng = random.Random(52313)
bundle = (root / 'build/cpu-gpu-kernel/linux-bundle.bin').read_bytes()
cases = [bytes(512), bytes([255])*512, bytes(range(256))*2,
         b'123456789'+bytes(503), bundle[:512], bundle[512:1024]]
cases += [rng.randbytes(512) for n in range(58)]
saved = [UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11]
results = []
for label, binary in (('original', (root/'build/dram-boot-voltage/loader.bin').read_bytes()),
                      ('fast', (folder/'loader.bin').read_bytes())):
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0x20000, 0x40000)
    uc.mem_write(0x44000, binary)
    instructions = [0]
    writes = []
    uc.hook_add(UC_HOOK_CODE, lambda *args: instructions.__setitem__(0, instructions[0]+1))
    uc.hook_add(UC_HOOK_MEM_WRITE, lambda machine, access, address, size, value, user: writes.append((address, size)))
    count = 0
    for i, data in enumerate(cases):
        for seed in (0xffffffff, 0x13579bdf):
            # An unaligned byte buffer is also part of the original function's contract.
            address = 0x31000 + (i % 4)
            uc.mem_write(address, data)
            uc.reg_write(UC_ARM_REG_CPSR, 0x1d3)
            uc.reg_write(UC_ARM_REG_SP, 0x2d000)
            uc.reg_write(UC_ARM_REG_LR, 0x5f000)
            uc.reg_write(UC_ARM_REG_R0, seed)
            uc.reg_write(UC_ARM_REG_R1, address)
            for n, reg in enumerate(saved):
                uc.reg_write(reg, 0x54321000+n)
            uc.emu_start(0x44454, 0x5f000, timeout=5_000_000, count=100000)
            assert uc.reg_read(UC_ARM_REG_PC) == 0x5f000
            expected = (~zlib.crc32(data, (~seed) & 0xffffffff)) & 0xffffffff
            assert uc.reg_read(UC_ARM_REG_R0) == expected, (label, i, seed)
            assert uc.reg_read(UC_ARM_REG_SP) == 0x2d000
            assert [uc.reg_read(reg) for reg in saved] == [0x54321000+n for n in range(8)]
            assert bytes(uc.mem_read(address, 512)) == data
            count += 1
    assert all(0x2cf00 <= address and address+size <= 0x2d000 for address, size in writes)
    results.append(dict(implementation=label, cases=count, result='PASS', instructions=instructions[0],
                        preserved_callee_saved_registers=True, writes_only_to_stack=True))
assert results[1]['instructions'] < results[0]['instructions'] / 4
manifest_path = folder/'loader.toc0.json'
manifest = json.loads(manifest_path.read_text())
manifest['ARM_emulation_verified'] = True
manifest['emulation'] = results
manifest_path.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8', newline='\n')
(root/'evidence/boot-fast-crc-emulation.json').write_text(json.dumps(dict(
    actual_patched_entry_executed=True, CRC_and_ABI_verified=True, tests=results,
    old_instruction_changed='0x44454', candidate_sha256=manifest['image_sha256']), indent=2)+'\n', encoding='utf-8')
print('ACTUAL_ARM_CRC_AND_ABI_EQUIVALENCE_PASS', json.dumps(results), flush=True)
