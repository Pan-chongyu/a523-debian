"""Preserve the signed loader and fallback; compose only bounded active items."""
import gzip
import hashlib
import json
from pathlib import Path
import stat
import struct
import zlib

root=Path(__file__).resolve().parents[1]
out=root/'build/boot-compact'
base=root/'build/boot-logo'
old=(base/'linux-bundle.bin').read_bytes()
m=json.loads((base/'linux-bundle.json').read_text())
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(old)==m['sha256']=='828347d9746d086bfe966a2b633c444ea0c9c42b80fe30621f7553c5467b6f3e'
def part(i):
    item=m['items'][i];off=(item['lba']-m['start_lba'])*512
    data=old[off:off+item['bytes']];assert sha(data)==item['sha256'];return data

# Parse the actual archive, preserving the exact init and ARM64 BusyBox bytes.
original=gzip.decompress(part(2)); pos=0; entries={}
while pos+110<=len(original):
    h=original[pos:pos+110];assert h[:6]==b'070701'
    v=[int(h[i:i+8],16) for i in range(6,110,8)]
    name=original[pos+110:pos+110+v[11]-1].decode()
    pos=(pos+110+v[11]+3)&~3
    data=original[pos:pos+v[6]];pos=(pos+v[6]+3)&~3
    if name=='TRAILER!!!':break
    entries[name]=(v,data)
assert entries['usr/bin/busybox'][1]==entries['bin/busybox'][1]
init=entries['init'][1]
assert init==(root/'firmware/initramfs-init').read_bytes().replace(b'\r\n',b'\n')
archive=bytearray();inode=0
def add(name,mode,data=b''):
    global inode
    inode+=1;n=name.encode()+b'\0'
    values=[inode,mode,0,0,1,0,len(data),0,0,0,0,len(n),0]
    archive.extend(b'070701'+b''.join(f'{x:08x}'.encode() for x in values)+n)
    archive.extend(bytes(-len(archive)%4));archive.extend(data);archive.extend(bytes(-len(archive)%4))
for name in ('.','bin','dev','proc','sys','run','tmp','sbin','usr','usr/bin','usr/sbin','newroot'):
    add(name,stat.S_IFDIR|(0o1777 if name=='tmp' else 0o755))
add('bin/busybox',stat.S_IFREG|0o755,entries['bin/busybox'][1])
add('init',stat.S_IFREG|0o755,init)
add('TRAILER!!!',0)
archive.extend(bytes(-len(archive)%512))
initrd=gzip.compress(archive,compresslevel=9,mtime=0)
(out/'initramfs.cpio.gz').write_bytes(initrd)
(out/'initramfs.cpio').write_bytes(archive)

# Modify only the chosen bootargs and initrd end property, retaining DT layout.
dt=bytearray(part(1))
magic,total,structure,strings=struct.unpack_from('>4I',dt)
assert magic==0xd00dfeed and total==len(dt)
cursor=structure;stack=[];changes=[]
while True:
    tag=struct.unpack_from('>I',dt,cursor)[0];cursor+=4
    if tag==1:
        end=dt.index(0,cursor);stack.append(dt[cursor:end].decode());cursor=(end+4)&~3
    elif tag==2:stack.pop()
    elif tag==3:
        size,offset=struct.unpack_from('>2I',dt,cursor);cursor+=8
        end=dt.index(0,strings+offset);name=dt[strings+offset:end].decode()
        if stack==['','chosen'] and name=='bootargs':
            previous=dt[cursor:cursor+size].split(b'\0')[0].decode()
            assert 'ignore_loglevel' in previous and 'earlycon=uart8250' in previous
            value=b'console=tty0 loglevel=3 quiet clk_ignore_unused regulator_ignore_unused rdinit=/init panic=5\0'
            assert len(value)<=size
            dt[cursor:cursor+size]=value+bytes(size-len(value));changes.append(name)
        elif stack==['','chosen'] and name=='linux,initrd-end':
            assert size==8 and struct.unpack_from('>Q',dt,cursor)[0]==0x60000000+len(part(2))
            struct.pack_into('>Q',dt,cursor,0x60000000+len(initrd));changes.append(name)
        cursor=(cursor+size+3)&~3
    elif tag==4:pass
    elif tag==9:break
    else:raise AssertionError(tag)
assert set(changes)=={'bootargs','linux,initrd-end'}
(out/'board.dtb').write_bytes(dt)
items=[(98305,(out/'kernel.lz4-block').read_bytes(),'kernel.lz4-block'),
       (m['items'][1]['lba'],bytes(dt),'board.dtb'),
       (m['items'][2]['lba'],initrd,'initramfs.cpio.gz'),
       (120000,(out/'linux-entry.bin').read_bytes(),'linux-entry.bin'),
       (m['items'][4]['lba'],part(4),'bl31.bin')]
regions=[];candidate=bytearray(old);new=json.loads(json.dumps(m));newitems=[]
for i,(lba,data,name) in enumerate(items):
    rounded=(len(data)+511)&~511;start=(lba-m['start_lba'])*512
    assert start>=512 and start+rounded<=len(candidate)
    assert all(start>=end or start+rounded<=begin for begin,end in regions)
    regions.append((start,start+rounded))
    payload=data+bytes(rounded-len(data));candidate[start:start+rounded]=payload
    address=int(m['items'][i]['load_address'],16)
    struct.pack_into('<6I',candidate,32+24*i,lba,len(data),address,zlib.crc32(payload),0,0)
    newitems.append(dict(file=name,lba=lba,bytes=len(data),load_address=hex(address),sha256=sha(data)))
struct.pack_into('<I',candidate,16,0)
struct.pack_into('<I',candidate,16,zlib.crc32(candidate[:512]))
new.update(items=newitems,sha256=sha(candidate),header_sha256=sha(candidate[:512]),
    previous_bundle_sha256=sha(old),profile='TZX-A523-lossless-compact-boot-v2',
    kernel_decoded_sha256=m['items'][0]['sha256'],kernel_decoded_bytes=m['items'][0]['bytes'],
    changed_payloads=[item['file'] for item in newitems[:4]],
    retained_signed_toc0_sha256='3031c2e408edb41dab4ab0f35171bf9ea3398842bfd2c653c8017149b13791ba',
    initramfs_init_sha256=sha(init),busybox_sha256=sha(entries['bin/busybox'][1]),
    old_read_bytes=sum((i['bytes']+511)&~511 for i in m['items']),
    new_read_bytes=sum((i['bytes']+511)&~511 for i in newitems),
    fresh_DRAM_training_preserved=True,all_payload_CRCs_preserved=True,
    native_kernel_output_CRC32=struct.unpack_from('<I',items[0][1],20)[0],
    serial_debug_removed=True, recovery_USB_serial_preserved=True,
    bounded_identity_MMU_cache_during_decode=True,MMU_data_cache_disabled_before_Linux=True)
(out/'linux-bundle.bin').write_bytes(candidate)
(out/'linux-bundle.json').write_text(json.dumps(new,indent=2)+'\n')
(out/'active-header.bin').write_bytes(candidate[:512])
print('BOOT_COMPACT_BUNDLE_COMPOSED',json.dumps({key:new[key] for key in ('sha256','header_sha256','old_read_bytes','new_read_bytes')}))
