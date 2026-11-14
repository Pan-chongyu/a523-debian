"""Pack only the new Image/entry in the spare slot; preserve other payloads."""
import hashlib,json,struct,zlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
source=root/'build/cpufreq-framework-kernel'
folder=root/'build/va48-kernel'
old=(source/'linux-bundle.bin').read_bytes()
before=json.loads((source/'linux-bundle.json').read_text())
build=json.loads((folder/'BUILD_COMPLETE.json').read_text())
sha=lambda data:hashlib.sha256(data).hexdigest()
assert sha(old)==before['sha256']=='3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
assert build['release']=='7.3.3-tzx-a523-va48' and build['kernel_build']==7
header=bytearray(512);header[:8]=b'A523BND1';struct.pack_into('<II',header,8,1,5)
bundle=bytearray(512);items=[]
for index,item in enumerate(before['items']):
    offset=(item['lba']-65536)*512
    saved=old[offset:offset+item['bytes']];assert sha(saved)==item['sha256']
    data=(folder/item['file']).read_bytes() if index in (0,3) else saved
    if index in (0,3):assert sha(data)==build['files'][item['file']]
    lba=98304+len(bundle)//512;block=data+bytes(-len(data)%512)
    struct.pack_into('<6I',header,32+index*24,lba,len(data),int(item['load_address'],16),zlib.crc32(block),0,0)
    bundle.extend(block)
    items.append(dict(file=item['file'],lba=lba,bytes=len(data),load_address=item['load_address'],sha256=sha(data)))
struct.pack_into('<I',header,16,zlib.crc32(header));bundle[:512]=header
assert 98304+len(bundle)//512<131072
record=dict(start_lba=98304,header_lba=4096,items=items,bytes=len(bundle),sectors=len(bundle)//512,
            sha256=sha(bundle),original_bundle_sha256=sha(old),changed_payloads=['Image','linux-entry.bin'],
            release=build['release'],hardware_boot_verified=False,
            full_ram_retained=True,purpose='48bit VA/PA translation comparison')
assert not (folder/'linux-bundle.bin').exists()
(folder/'linux-bundle.bin').write_bytes(bundle)
(folder/'linux-bundle.json').write_text(json.dumps(record,indent=2)+'\n')
print('VA48_BUNDLE_COMPOSED',json.dumps(record,indent=2))
