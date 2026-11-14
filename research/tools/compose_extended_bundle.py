"""Stage the additive swap/video kernel without touching the active boot slot."""
import hashlib
import json
from pathlib import Path
import struct
import zlib

root=Path(__file__).resolve().parents[1]
before=root/'build/screen-boot-kernel';out=root/'build/extended-kernel'
old=(before/'linux-bundle.bin').read_bytes()
old_manifest=json.loads((before/'linux-bundle.json').read_text())
assert hashlib.sha256(old).hexdigest()==old_manifest['sha256']=='f6b644da1a8276b599c9e3f6b7944c6eb246ddd8c8adf0cbe5ba20116c6a3829'
audit=json.loads((out/'module-audit/complete.json').read_text())
active=[r for r in audit if not any(s in r['before'] for s in ('/tzx-battery-peripheral/','/tzx-touch-peripheral/','/tzx-bt-runtime/'))]
assert len(active)>55 and all(r['equal_after_normalizing_source_directory'] for r in active)
header=bytearray(512);header[:8]=b'A523BND1';struct.pack_into('<II',header,8,1,5)
bundle=bytearray(512);items=[]
for i,item in enumerate(old_manifest['items']):
    offset=(item['lba']-98304)*512;original=old[offset:offset+item['bytes']]
    assert hashlib.sha256(original).hexdigest()==item['sha256']
    payload=(out/item['file']).read_bytes() if i in (0,1,3) else original
    if i in (2,4): (out/item['file']).write_bytes(payload)
    padded=payload+bytes(-len(payload)%512);lba=65536+len(bundle)//512
    struct.pack_into('<6I',header,32+i*24,lba,len(payload),int(item['load_address'],16),zlib.crc32(padded),0,0)
    items.append(dict(file=item['file'],lba=lba,bytes=len(payload),load_address=item['load_address'],sha256=hashlib.sha256(payload).hexdigest()))
    bundle.extend(padded)
struct.pack_into('<I',header,16,zlib.crc32(header));bundle[:512]=header
assert 65536+len(bundle)//512<98304
manifest=dict(start_lba=65536,header_lba=4096,bytes=len(bundle),sectors=len(bundle)//512,
              sha256=hashlib.sha256(bundle).hexdigest(),header_sha256=hashlib.sha256(header).hexdigest(),
              previous_bundle_sha256=old_manifest['sha256'],previous_start_lba=98304,
              config_sha256=hashlib.sha256((out/'kernel.config').read_bytes()).hexdigest(),
              config_change='SWAP, ZRAM/LZ4, DMA_HEAP_SYSTEM, sun55i IOMMU for VE0/VE1 only',items=items,
              module_compatibility='recompiled allocatable code/data equal; __FILE__ directory normalized; MODVERSIONS disabled',
              changed_payloads=['Image','board.dtb','linux-entry.bin'],unchanged_payloads=['initramfs.cpio.gz','bl31.bin'],hardware_boot_verified=False)
(out/'linux-bundle.bin').write_bytes(bundle)
(out/'linux-bundle.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({k:manifest[k] for k in ('bytes','sha256','header_sha256','config_sha256')},indent=2))
