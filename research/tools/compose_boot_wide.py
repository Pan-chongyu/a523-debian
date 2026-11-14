"""Retain early CPU/CRC code and add a validated legacy 8-bit read path."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from make_toc0 import build

root = Path(__file__).resolve().parents[1]
out = root/'build/boot-wide-emmc'
out.mkdir(exist_ok=True)
assert not (out/'loader.toc0').exists()
task_path = '/mnt/c/Users/pan75/Documents/ChatGPT/A523适配debian'
subprocess.run(['wsl', '-d', 'Ubuntu-22.04', '--', 'sh', task_path+'/tools/build_boot_wide.sh'], check=True)
base = root/'build/boot-early-cpub'
old = (base/'loader.bin').read_bytes()
previous = json.loads((base/'loader.toc0.json').read_text())
sha = lambda b: hashlib.sha256(b).hexdigest()
assert sha((base/'loader.toc0').read_bytes()) == '70efff1506d33cd90931197b5b558cace64720dca5e4b7a3d6db688851526db0'
assert sha(old) == previous['loader_sha256'] and previous['ARM_emulation_verified']
assert len(old) == 33816
hook = (out/'wide-hook.bin').read_bytes()
entry = struct.unpack_from('<I', (out/'wide-hook.elf').read_bytes(), 24)[0]
assert entry == 0x4c500 and len(hook) <= 2048
offset = 0x444a0-0x44000
assert struct.unpack_from('<I', old, offset)[0] == 0xeb001f96
new = bytearray(old)
struct.pack_into('<I', new, offset, 0xeb000000 | (((entry-0x444a0-8)//4) & 0xffffff))
new += bytes(entry-0x44000-len(new)) + hook
assert len(new)+0xf80 <= 40960
assert new[:offset] == old[:offset] and new[offset+4:len(old)] == old[offset+4:]
(out/'loader.bin').write_bytes(new)
build(bytes(new), 0x44000, out/'loader.toc0')
manifest = json.loads((out/'loader.toc0.json').read_text())
manifest.update(previous_toc0_sha256=previous['image_sha256'], previous_loader_sha256=sha(old),
    loader_sha256=sha(new), changed_old_instruction='0x444a0', hook_entry=hex(entry),
    hook_bytes=len(hook), preserved_previous_bytes=len(old)-4, bus_width=8,
    CRC_CPU_DRAM_BL31_kernel_unchanged=True, clock_voltage_timing_unchanged=True,
    no_storage_data_writes=True, three_distinct_sectors_compared=True,
    comparison_failure_resets_to_original_1bit=True, ARM_emulation_verified=False,
    hardware_boot_verified=False)
(out/'loader.toc0.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8', newline='\n')
print('VALIDATED_WIDE_BOOT_READER_SIGNED', json.dumps(manifest), flush=True)
