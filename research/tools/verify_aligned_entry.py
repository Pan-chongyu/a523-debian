"""Execute the real AArch64 entry binary and overlapping move in Unicorn."""
from pathlib import Path
import hashlib
import json
import struct
import sys
import argparse

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'build/host-unicorn'))
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3

parser = argparse.ArgumentParser()
parser.add_argument('--artifact-dir', default='build/peripheral-kernel')
parser.add_argument('--output', default='evidence/aligned-entry-emulation.json')
args = parser.parse_args()
entry = (root/args.artifact_dir/'linux-entry.bin').read_bytes()
image = (root/args.artifact_dir/'Image').read_bytes()
size = struct.unpack_from('<Q', image, 16)[0]
assert image[0x38:0x3c] == b'ARM\x64' and 0 < len(image) <= size < 0x1f80000
copy_bytes = (len(image) + 511) // 512 * 512
results = []
for case in ['actual_image', 'nonzero_offset', 'zero_size', 'oversize', 'unaligned_size']:
    machine = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    for address, length in [(0x48000000, 0x2000000), (0x4a000000, 0x1000), (0x07090000, 0x1000), (0x02050000, 0x1000)]:
        machine.mem_map(address, length)
    for i in range(16):
        machine.mem_map(0x41000000 + i*0x10000000, 0x1000)
    payload = bytearray(image + b'\xa5'*(copy_bytes-len(image)))
    if case == 'nonzero_offset': struct.pack_into('<Q', payload, 8, 0x80000)
    if case == 'zero_size': struct.pack_into('<Q', payload, 16, 0)
    if case == 'oversize': struct.pack_into('<Q', payload, 16, 0x2000000)
    if case == 'unaligned_size': struct.pack_into('<Q', payload, 16, size+1)
    machine.mem_write(0x48080000, bytes(payload))
    machine.mem_write(0x4a000000, entry)
    machine.emu_start(0x4a000000, 0x48000000, timeout=20_000_000, count=5_000_000 if case == 'actual_image' else 2000)
    if case == 'actual_image':
        assert machine.reg_read(UC_ARM64_REG_PC) == 0x48000000
        moved = bytes(machine.mem_read(0x48000000, copy_bytes))
        assert moved == payload
        assert machine.reg_read(UC_ARM64_REG_X0) == 0x47000000
        assert all(machine.reg_read(reg) == 0 for reg in [UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3])
        assert bytes(machine.mem_read(0x07090110, 4)) == struct.pack('<I', 0xa5233303)
        results.append({'case': case, 'bytes_compared': copy_bytes, 'image_size': size, 'sha256': hashlib.sha256(moved).hexdigest(), 'result': 'PASS'})
    else:
        assert bytes(machine.mem_read(0x07090110, 4)) == struct.pack('<I', 0xa52333ee)
        assert bytes(machine.mem_read(0x02050008, 4)) == struct.pack('<I', 0x16aa0001)
        results.append({'case': case, 'result': 'REJECTED_AS_EXPECTED'})
text = json.dumps({'entry_sha256': hashlib.sha256(entry).hexdigest(), 'tests': results}, indent=2)
(root/args.output).write_text(text+'\n')
print(text)
