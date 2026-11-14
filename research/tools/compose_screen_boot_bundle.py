"""Put the rotation-enabled kernel in the spare slot; preserve all board payloads."""
import hashlib
import json
from pathlib import Path
import struct
import zlib

root = Path(__file__).resolve().parents[1]
before = root/'build/cpufreq-framework-kernel'
out = root/'build/screen-boot-kernel'
old = (before/'linux-bundle.bin').read_bytes()
old_manifest = json.loads((before/'linux-bundle.json').read_text())
assert hashlib.sha256(old).hexdigest() == old_manifest['sha256'] == '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
assert not json.loads((out/'ABI.json').read_text())['changed']
header = bytearray(512)
header[:8] = b'A523BND1'
struct.pack_into('<II', header, 8, 1, 5)
bundle = bytearray(512)
items = []
for i, item in enumerate(old_manifest['items']):
    offset = (item['lba']-65536)*512
    original = old[offset:offset+item['bytes']]
    assert hashlib.sha256(original).hexdigest() == item['sha256']
    payload = (out/item['file']).read_bytes() if i in (0, 3) else original
    if i not in (0, 3):
        (out/item['file']).write_bytes(payload)
    padded = payload + bytes(-len(payload) % 512)
    lba = 98304 + len(bundle)//512
    struct.pack_into('<6I', header, 32+i*24, lba, len(payload), int(item['load_address'], 16), zlib.crc32(padded), 0, 0)
    items.append(dict(file=item['file'], lba=lba, bytes=len(payload), load_address=item['load_address'],
                      sha256=hashlib.sha256(payload).hexdigest()))
    bundle.extend(padded)
struct.pack_into('<I', header, 16, zlib.crc32(header))
bundle[:512] = header
assert 98304 + len(bundle)//512 < 131072
manifest = dict(start_lba=98304, header_lba=4096, bytes=len(bundle), sectors=len(bundle)//512,
                sha256=hashlib.sha256(bundle).hexdigest(), header_sha256=hashlib.sha256(header).hexdigest(),
                previous_bundle_sha256=old_manifest['sha256'], previous_start_lba=65536,
                config_sha256=hashlib.sha256((out/'kernel.config').read_bytes()).hexdigest(),
                config_change='CONFIG_FRAMEBUFFER_CONSOLE_ROTATION=y', items=items,
                changed_payloads=['Image', 'linux-entry.bin'], unchanged_payloads=['board.dtb', 'initramfs.cpio.gz', 'bl31.bin'],
                hardware_boot_verified=False)
(out/'linux-bundle.bin').write_bytes(bundle)
(out/'linux-bundle.json').write_text(json.dumps(manifest, indent=2)+'\n')
print(json.dumps({k: manifest[k] for k in ('bytes', 'sha256', 'header_sha256', 'config_sha256')}, indent=2))
