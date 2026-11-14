"""Change only kpti=0 in the original #5 DTB for a TTBR-switch comparison."""
import hashlib,json,struct,zlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
folder=root/'build/kpti-off-trial';folder.mkdir(exist_ok=False)
base=root/'build/cpufreq-framework-kernel'
old=(base/'linux-bundle.bin').read_bytes();before=json.loads((base/'linux-bundle.json').read_text())
sha=lambda data:hashlib.sha256(data).hexdigest()
assert sha(old)==before['sha256']=='3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
item=before['items'][1];start=(item['lba']-65536)*512
original=old[start:start+item['bytes']]
dtb=bytearray(original[:struct.unpack_from('>I',original,4)[0]])
bootargs=b'console=tty0 console=ttyS0,115200 earlycon=uart8250,mmio32,0x02500000,115200 loglevel=8 ignore_loglevel clk_ignore_unused regulator_ignore_unused rdinit=/init panic=5\0'
assert dtb.count(bootargs)==1
position=dtb.index(bootargs)
assert struct.unpack_from('>II',dtb,position-12)==(3,len(bootargs))
newargs=bootargs[:-1]+b' kpti=0\0';newregion=newargs+bytes(-len(newargs)%4)
oldregion=(len(bootargs)+3)&~3;delta=len(newregion)-oldregion
dtb[position:position+oldregion]=newregion
struct.pack_into('>I',dtb,position-8,len(newargs))
for offset in (4,12,36):struct.pack_into('>I',dtb,offset,struct.unpack_from('>I',dtb,offset)[0]+delta)
(folder/'board.dtb').write_bytes(dtb)
header=bytearray(512);header[:8]=b'A523BND1';struct.pack_into('<II',header,8,1,5)
bundle=bytearray(512);items=[]
for index,item in enumerate(before['items']):
    offset=(item['lba']-65536)*512;saved=old[offset:offset+item['bytes']]
    assert sha(saved)==item['sha256']
    data=bytes(dtb) if index==1 else saved
    lba=98304+len(bundle)//512;block=data+bytes(-len(data)%512)
    struct.pack_into('<6I',header,32+index*24,lba,len(data),int(item['load_address'],16),zlib.crc32(block),0,0)
    bundle.extend(block)
    items.append(dict(file=item['file'],lba=lba,bytes=len(data),load_address=item['load_address'],sha256=sha(data)))
struct.pack_into('<I',header,16,zlib.crc32(header));bundle[:512]=header
assert 98304+len(bundle)//512<131072
record=dict(start_lba=98304,header_lba=4096,items=items,bytes=len(bundle),sectors=len(bundle)//512,
 sha256=sha(bundle),original_bundle_sha256=sha(old),changed_payloads=['board.dtb'],
 hardware_boot_verified=False,purpose='diagnostic kpti=0, full4GiB and original#5',
 bootargs_before=bootargs[:-1].decode(),bootargs_after=newargs[:-1].decode())
(folder/'linux-bundle.bin').write_bytes(bundle)
(folder/'linux-bundle.json').write_text(json.dumps(record,indent=2)+'\n')
print('KPTI_OFF_BUNDLE_COMPOSED',sha(bundle),len(bundle),sha(dtb),len(dtb))
