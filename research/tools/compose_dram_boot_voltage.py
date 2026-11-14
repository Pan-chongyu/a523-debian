"""Replace one empty hook in the frozen loader; retain all other old bytes."""
import hashlib
import json
from pathlib import Path
import struct
from fel_device import ROOT
from make_toc0 import build

out = ROOT/'build/dram-boot-voltage'
old_toc = (ROOT/'build/known-good-loader/chain-loader.toc0').read_bytes()
old = (ROOT/'build/known-good-loader/chain-loader.bin').read_bytes()
assert hashlib.sha256(old_toc).hexdigest() == 'ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df'
assert hashlib.sha256(old).hexdigest() == 'bb133505c750f2594490212633bd29b594cfec351b64f3095c07ad96129e0acd'
assert old_toc[0xf80:0xf80+len(old)] == old
hook = (out/'voltage-hook.bin').read_bytes()
elf = (out/'voltage-hook.elf').read_bytes()
entry = struct.unpack_from('<I', elf, 24)[0]
assert 0x4b900 <= entry < 0x4c900 and len(hook) < 4096
assert len(old) == 0x78dc
offset = 0x44168-0x44000
assert old[offset:offset+8] == struct.pack('<II', 0xe3a00000, 0xe12fff1e)
assert not (entry-0x44168-8) & 3
branch = 0xea000000 | (((entry-0x44168-8)//4) & 0xffffff)
candidate = bytearray(old)
struct.pack_into('<I', candidate, offset, branch)
candidate += bytes(0x4b900-0x44000-len(candidate)) + hook
assert candidate[:offset] == old[:offset] and candidate[offset+4:len(old)] == old[offset+4:]
assert candidate[0x78dc:0x78e4] == bytes(8)  # old BSS remains clearable
assert len(candidate)+0xf80 <= 40960
(out/'loader.bin').write_bytes(candidate)
build(bytes(candidate), 0x44000, out/'loader.toc0')
manifest_path = out/'loader.toc0.json'
manifest = json.loads(manifest_path.read_text())
manifest['reused_executable_bytes'] = len(old)-4
manifest['retained_frozen_loader_sha256'] = hashlib.sha256(old).hexdigest()
manifest['changed_old_instruction_addresses'] = ['0x44168']
manifest_path.write_text(json.dumps(manifest, indent=2)+'\n')
record = {'original_toc0_sha256': hashlib.sha256(old_toc).hexdigest(),
          'original_loader_bytes': len(old), 'old_bytes_changed': [hex(0x44168)],
          'hook_entry': hex(entry), 'hook_text_start': '0x4b900', 'hook_bytes': len(hook),
          'candidate_sha256': hashlib.sha256(candidate).hexdigest(),
          'voltage_set_before_training': True, 'requested_mV': 1260,
          'mmc_reader_unchanged': True, 'kernel_DTB_BL31_unchanged': True,
          'emulator_verified': False, 'hardware_tested': False}
(out/'HOOK_CHANGE.json').write_text(json.dumps(record, indent=2)+'\n')
print('DRAM_BOOT_HOOK_ONLY_PACKAGE', json.dumps(record))
