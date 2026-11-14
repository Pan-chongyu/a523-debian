"""Overlap the full minimum panel rail settling interval with DRAM training."""
import hashlib
import json
import os
import struct
import subprocess
from pathlib import Path

from make_toc0 import build

root = Path(__file__).resolve().parents[1]
folder = root/'build/boot-logo-overlap'
folder.mkdir(exist_ok=True)
script = root/'tools/build_boot_logo_overlap.sh'
if os.name == 'nt':
    script_path = '/mnt/'+root.drive[0].lower()+script.as_posix()[2:]
    command = ['wsl', '-d', os.environ.get('TZX_WSL_DISTRO', 'Ubuntu-22.04'), '--', 'sh', script_path]
else:
    command = ['sh', str(script)]
subprocess.run(command, check=True)
base = root/'build/boot-logo'
before = (base/'sram-loader.bin').read_bytes()
sha = lambda data: hashlib.sha256(data).hexdigest()
original = json.loads((base/'loader.toc0.json').read_text())
assert sha((base/'loader.toc0').read_bytes()) == 'fc208e752fc816e1e016944cd0f4c4d9497989ec174718e5f3b12d030136b0ca'
symbols = {items[2]: int(items[0], 16) for line in (folder/'speed.symbols.txt').read_text().splitlines()
           if len(items := line.split()) == 3}
candidate = bytearray(before)
patches = []
for address, was, value, reason in (
    (0x44168, 0xea002499, 0xea000000 | (((symbols['boot_panel_performance_entry']-0x44168-8)//4)&0xffffff), 'Prepare panel rail then boost CPU before training'),
    (0x4e6d8, 0xe12fff33, 0xe3a00000, 'Do not initialize eMMC until DRAM is ready'),
    (0x4ea90, 0x4e6a4, symbols['boot_logo_speed_card_init'], 'Finish settled panel then initialize the original card path'),
    (0x4441c, 0xe8bd81f0, 0xea000000 | (((symbols['boot_logo_speed_outer_return']-0x4441c-8)//4)&0xffffff), 'Restore CPU and cancel a pending panel on any outer return')):
    offset = address-0x44000
    assert struct.unpack_from('<I', candidate, offset)[0] == was
    struct.pack_into('<I', candidate, offset, value)
    patches.append(dict(address=address, old=was, new=value, reason=reason))
panel_text = (folder/'panel-text.bin').read_bytes()
panel_rodata = (folder/'panel-rodata.bin').read_bytes()
speed = (folder/'speed.bin').read_bytes()
assert len(panel_text) <= 0x1200 and len(panel_rodata) <= 0x180
assert len(speed) < 0x4ef00-0x4eac0
candidate += bytes(0x4f080-0x44000-len(candidate))
for address, data in ((0x4d000, panel_text), (0x4eac0, speed), (0x4ef00, panel_rodata)):
    candidate[address-0x44000:address-0x44000+len(data)] = data
# Retain the entire original CPU voltage/clock module and the logo loader.
expected_cpu = bytearray(before[0x4e200-0x44000:0x4e898-0x44000])
struct.pack_into('<I', expected_cpu, 0x4e6d8-0x4e200, 0xe3a00000)
assert candidate[0x4e200-0x44000:0x4e898-0x44000] == expected_cpu
assert candidate[0x4b85c-0x44000:0x4b8dc-0x44000] == before[0x4b85c-0x44000:0x4b8dc-0x44000]
(folder/'sram-loader.bin').write_bytes(candidate)
build(bytes(candidate), 0x44000, folder/'loader.toc0')
manifest = json.loads((folder/'loader.toc0.json').read_text())
manifest.update(previous_toc0_sha256=original['image_sha256'], previous_loader_sha256=sha(before),
                loader_sha256=sha(candidate), code_patches=patches,
                replacements=[dict(address=address, bytes=len(data), sha256=sha(data), staged_name=name)
                              for address, data, name in ((0x4d000, panel_text, 'panel-text.bin'),
                                                         (0x4eac0, speed, 'speed.bin'),
                                                         (0x4ef00, panel_rodata, 'panel-rodata.bin'))],
                original_firmware_bytes=len(before),
                original_logo_payload_sha256=original['payload_sha256'],
                original_logo_framebuffer_sha256=original['native_bgra_sha256'],
                DRAM_parameters_geometry_scanning_and_fresh_training_unchanged=True,
                panel_rail_minimum_settle_us=1000000,
                panel_reset_DSI_wake_and_scan_waits_unchanged=True,
                overlap_receipt_address=0x2d740,
                CPUA_qualified_khz=1416000, CPUA_qualified_mv=1150,
                restore_on_DRAM_failure_and_before_TFA=True,
                photo_and_decoder_unchanged=True,
                ARM_emulation_verified=False, hardware_boot_verified=False)
(folder/'loader.toc0.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
print('PANEL_SETTLE_DRAM_OVERLAP_CANDIDATE', manifest['image_sha256'], len(candidate), flush=True)
