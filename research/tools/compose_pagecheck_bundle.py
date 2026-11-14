"""Stage a diagnostic #6 kernel separately; preserve every #5 boot payload."""
import hashlib
import json
from pathlib import Path
import struct
import zlib

root = Path(__file__).resolve().parents[1]
source = root/'build/cpufreq-framework-kernel'
target = root/'build/pagecheck-kernel'
old = (source/'linux-bundle.bin').read_bytes()
before = json.loads((source/'linux-bundle.json').read_text())
assert hashlib.sha256(old).hexdigest() == before['sha256'] == '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
assert before['start_lba'] == 65536 and before['header_lba'] == 4096
build = json.loads((target/'BUILD_COMPLETE.json').read_text())
assert build['kernel_build'] == 6 and not build['changed']
header = bytearray(512)
header[:8] = b'A523BND1'
struct.pack_into('<II', header, 8, 1, 5)
bundle = bytearray(512)
storage_lba = 98304
items = []
for index, item in enumerate(before['items']):
    offset = (item['lba'] - before['start_lba'])*512
    saved = old[offset:offset+item['bytes']]
    assert hashlib.sha256(saved).hexdigest() == item['sha256']
    data = (target/item['file']).read_bytes() if index in (0, 3) else saved
    if index in (0, 3):
        assert hashlib.sha256(data).hexdigest() == build['files'][item['file']]
    lba = storage_lba + len(bundle)//512
    padded = data + bytes(-len(data) % 512)
    struct.pack_into('<6I', header, 32+index*24, lba, len(data),
                     int(item['load_address'], 16), zlib.crc32(padded), 0, 0)
    items.append(dict(file=item['file'], lba=lba, bytes=len(data),
                      load_address=item['load_address'], sha256=hashlib.sha256(data).hexdigest()))
    bundle.extend(padded)
struct.pack_into('<I', header, 16, zlib.crc32(header))
bundle[:512] = header
assert storage_lba + len(bundle)//512 < 131072
manifest = dict(start_lba=storage_lba, header_lba=4096, items=items,
                bytes=len(bundle), sectors=len(bundle)//512,
                sha256=hashlib.sha256(bundle).hexdigest(), hardware_boot_verified=False,
                original_bundle_sha256=before['sha256'], changed_payloads=['Image', 'linux-entry.bin'],
                unchanged_payloads=['board.dtb', 'initramfs.cpio.gz', 'bl31.bin'])
assert not (target/'linux-bundle.bin').exists()
(target/'linux-bundle.bin').write_bytes(bundle)
(target/'linux-bundle.json').write_text(json.dumps(manifest, indent=2)+'\n')
print('PAGECHECK_BUNDLE_COMPOSED', json.dumps(manifest, indent=2))
