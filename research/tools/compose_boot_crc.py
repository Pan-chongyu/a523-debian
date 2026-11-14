"""Retain the trained loader; replace one CRC entry instruction with a branch."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

from make_toc0 import build

root = Path(__file__).resolve().parents[1]
out = root / 'build/boot-latency-loader'
out.mkdir(exist_ok=True)
assert not (out / 'loader.toc0').exists()
table = []
for n in range(256):
    value = n
    for bit in range(8):
        value = (value >> 1) ^ (0xedb88320 if value & 1 else 0)
    table.append(value)
(out / 'boot_crc_table.h').write_text('static const uint32_t boot_crc_table[256] = {\n' +
    ',\n'.join('    ' + ', '.join('0x%08xU' % v for v in table[i:i+8])
               for i in range(0, 256, 8)) + '\n};\n', encoding='ascii', newline='\n')
task_path = '/mnt/c/Users/pan75/Documents/ChatGPT/A523适配debian'
subprocess.run(['wsl', '-d', 'Ubuntu-22.04', '--', 'sh', task_path + '/tools/build_boot_crc.sh'], check=True)
old = (root / 'build/dram-boot-voltage/loader.bin').read_bytes()
old_toc = (root / 'build/dram-boot-voltage/loader.toc0').read_bytes()
sha = lambda b: hashlib.sha256(b).hexdigest()
assert sha(old) == '97c38bf6d21fd12609a9fa9e6c567c08757983f2fed4908bced0e56d0b4c5b29'
assert sha(old + bytes(-len(old) % 32)) == 'bd0593c446e9179e35a12ed1a0d0e3fb31e21b97c9dffa64ff11ce2c7c6bca45'
assert sha(old_toc) == '311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75'
assert old_toc[0xf80:0xf80+len(old)] == old
hook = (out / 'crc-hook.bin').read_bytes()
entry = struct.unpack_from('<I', (out / 'crc-hook.elf').read_bytes(), 24)[0]
assert entry == 0x4be00 and len(hook) <= 1536
assert len(old) == 32036 and 0x44000 + len(old) <= entry
offset = 0x44454 - 0x44000
assert old[offset:offset+4] == struct.pack('<I', 0xe52de004)
branch = 0xea000000 | (((entry - 0x44454 - 8) // 4) & 0xffffff)
new = bytearray(old)
struct.pack_into('<I', new, offset, branch)
new += bytes(entry - 0x44000 - len(new)) + hook
assert new[:offset] == old[:offset] and new[offset+4:len(old)] == old[offset+4:]
assert len(new) + 0xf80 <= 40960
(out / 'loader.bin').write_bytes(new)
build(bytes(new), 0x44000, out / 'loader.toc0')
manifest = json.loads((out / 'loader.toc0.json').read_text())
manifest.update(original_toc0_sha256=sha(old_toc), original_loader_sha256=sha(old),
    loader_sha256=sha(new), old_instruction_changed='0x44454', hook_entry=hex(entry),
    hook_bytes=len(hook), preserved_old_bytes=len(old)-4, checksum_algorithm='CRC32/IEEE identical, 512 bytes per call',
    mmc_DRAM_PMIC_CPU_BL31_kernel_unchanged=True, ARM_emulation_verified=False,
    hardware_boot_verified=False)
(out / 'loader.toc0.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
print('FAST_CRC_SIGNED_LOADER_BUILT', json.dumps(manifest), flush=True)
