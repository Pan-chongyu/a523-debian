"""Keep every #5 payload except BL31; place the trial in the previous #6 slot."""
import hashlib
import json
from pathlib import Path
import struct
import zlib

root = Path(__file__).resolve().parents[1]
folder = root/'build/bl31-prefetch'
before = json.loads((root/'build/cpufreq-framework-kernel/linux-bundle.json').read_text())
old = (root/'build/cpufreq-framework-kernel/linux-bundle.bin').read_bytes()
build = json.loads((folder/'BUILD_COMPLETE.json').read_text())
sha = lambda data: hashlib.sha256(data).hexdigest()
assert sha(old) == before['sha256'] == '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
assert build['expected_cpuectlr'] == '0x28081000'
header = bytearray(512)
header[:8] = b'A523BND1'
struct.pack_into('<II', header, 8, 1, 5)
bundle = bytearray(512)
items = []
for index, item in enumerate(before['items']):
    offset = (item['lba']-65536)*512
    data = old[offset:offset+item['bytes']]
    assert sha(data) == item['sha256']
    if item['file'] == 'bl31.bin':
        data = (folder/'bl31.bin').read_bytes()
        assert sha(data) == build['files']['bl31.bin']
    lba = 98304+len(bundle)//512
    padded = data+bytes(-len(data)%512)
    struct.pack_into('<6I', header, 32+24*index, lba, len(data), int(item['load_address'],16),
                     zlib.crc32(padded), 0, 0)
    bundle.extend(padded)
    items.append(dict(file=item['file'], lba=lba, bytes=len(data),
                      load_address=item['load_address'], sha256=sha(data)))
struct.pack_into('<I', header, 16, zlib.crc32(header))
bundle[:512] = header
assert 98304+len(bundle)//512 < 131072
manifest = dict(start_lba=98304, header_lba=4096, bytes=len(bundle), sectors=len(bundle)//512,
    sha256=sha(bundle), items=items, original_bundle_sha256=sha(old),
    changed_payloads=['bl31.bin'], unchanged_payloads=[x['file'] for x in items if x['file']!='bl31.bin'],
    hardware_boot_verified=False, purpose='bounded diagnostic; disable A55 L1/L3 data prefetch before MMU enable')
assert not (folder/'linux-bundle.bin').exists()
(folder/'linux-bundle.bin').write_bytes(bundle)
(folder/'linux-bundle.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
