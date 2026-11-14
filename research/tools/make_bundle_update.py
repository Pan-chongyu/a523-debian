"""Generate an exact-image eMMC update for the board's reserved boot gap."""
import argparse,hashlib,json,struct,zlib
from fel_device import ROOT,EXPECTED_CID
p=argparse.ArgumentParser()
p.add_argument('--bundle-dir',default='build')
a=p.parse_args()
b=(ROOT/a.bundle_dir).resolve()
b.relative_to(ROOT.resolve())
manifest=json.loads((b/'linux-bundle.json').read_text())
data=(b/'linux-bundle.bin').read_bytes()
assert hashlib.sha256(data).hexdigest()==manifest['sha256']
assert len(data)==manifest['bytes'] and 2097152+len(data)<67108864
assert len(data)%512==0 and manifest['sectors']==len(data)//512
assert data[:8]==b'A523BND1' and struct.unpack_from('<II',data,8)==(1,5)
header=bytearray(data[:512]);expected=struct.unpack_from('<I',header,16)[0]
struct.pack_into('<I',header,16,0)
assert zlib.crc32(header)==expected
for i,item in enumerate(manifest['items']):
    lba,size,address,crc,_,_=struct.unpack_from('<6I',data,32+24*i)
    assert lba==item['lba'] and size==item['bytes'] and address==int(item['load_address'],16)
    offset=(lba-4096)*512;rounded=(size+511)&~511
    assert offset>=512 and offset+rounded<=len(data)
    assert zlib.crc32(data[offset:offset+rounded])==crc
    assert hashlib.sha256(data[offset:offset+size]).hexdigest()==item['sha256']
script=f'''#!/bin/sh
set -eu
test "$(cat /sys/class/block/mmcblk0/device/cid)" = '{EXPECTED_CID}'
test "$(blockdev --getsz /dev/mmcblk0)" = '244318208'
test "$(blkid -s PTUUID -o value /dev/mmcblk0)" = 'c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
test "$(sha256sum /home/debian/linux-bundle.bin | cut -d ' ' -f1)" = '{manifest['sha256']}'
dd if=/home/debian/linux-bundle.bin of=/dev/mmcblk0 bs=65536 seek=32 conv=fsync
actual=$(dd if=/dev/mmcblk0 bs=512 skip=4096 count={manifest['sectors']} status=none | sha256sum | cut -d ' ' -f1)
test "$actual" = '{manifest['sha256']}'
echo UPDATED_BUNDLE_FULL_READBACK_PASS:$actual
'''
script+='mkdir -p /home/debian/current-bundle\n'
for item in manifest['items'][:3]:
    script+=(f"dd if=/home/debian/linux-bundle.bin of=/home/debian/current-bundle/{item['file']} "
             f"bs=512 skip={item['lba']-4096} count={(item['bytes']+511)//512} status=none\n"
             f"truncate -s {item['bytes']} /home/debian/current-bundle/{item['file']}\n"
             f"test \"$(sha256sum /home/debian/current-bundle/{item['file']} | cut -d ' ' -f1)\" = '{item['sha256']}'\n"
             f"cp /home/debian/current-bundle/{item['file']} /boot/{item['file']}\n")
script+='sync\n'
(b/'update-linux-bundle.sh').write_text(script,encoding='ascii',newline='\n')
print('Generated exact bundle update:',manifest['sha256'])
