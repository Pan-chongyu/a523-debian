"""Read-only verification of the selected relocated candidate and rollback slot."""
import hashlib
import json
import os
from pathlib import Path
import struct
import uuid
import zlib

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/class/block/mmcblk0/size').read_text().strip() == '244318208'
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
sha = lambda data: hashlib.sha256(data).hexdigest()
manifest = json.loads(Path('/home/debian/installed-bundle.json').read_text())
assert (manifest['start_lba'],manifest['header_lba'],manifest['bytes'],manifest['sha256']) == (
    98304,4096,14880768,'165f940df7bcd97bddce20ec927d53fe32bcf3581fadbd3c10c5404484671e8a')
fd = os.open('/dev/mmcblk0',os.O_RDONLY)
try:
    toc = os.pread(fd,40960,256*512)
    assert sha(toc) == 'ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df'
    gpt = os.pread(fd,512,512)
    assert gpt[:8] == b'EFI PART' and str(uuid.UUID(bytes_le=gpt[56:72])) == 'c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
    checked = bytearray(gpt)
    checksum = struct.unpack_from('<I',checked,16)[0]
    struct.pack_into('<I',checked,16,0)
    assert zlib.crc32(checked[:struct.unpack_from('<I',checked,12)[0]]) == checksum
    lba,count,stride,checksum = struct.unpack_from('<QIII',gpt,72)
    assert stride >= 128 and 0 < count*stride <= 65536
    table = os.pread(fd,count*stride,lba*512)
    assert zlib.crc32(table) == checksum
    first = min(struct.unpack_from('<Q',table,i*stride+32)[0] for i in range(count)
                if any(table[i*stride:i*stride+16]))
    assert first == 131072 and 98304+manifest['bytes']//512 < first
    candidate = os.pread(fd,manifest['bytes'],98304*512)
    assert len(candidate) == manifest['bytes'] and sha(candidate) == manifest['sha256']
    header = os.pread(fd,512,4096*512)
    assert header == candidate[:512] and header[:8] == b'A523BND1'
    checked = bytearray(header)
    checksum = struct.unpack_from('<I',checked,16)[0]
    struct.pack_into('<I',checked,16,0)
    assert zlib.crc32(checked) == checksum
    for i,item in enumerate(manifest['items']):
        lba,length,address,checksum,r1,r2 = struct.unpack_from('<6I',header,32+i*24)
        assert (lba,length,address,r1,r2) == (item['lba'],item['bytes'],int(item['load_address'],16),0,0)
        offset = (lba-98304)*512
        payload = candidate[offset:offset+length]
        padded = candidate[offset:offset+(length+511)//512*512]
        assert sha(payload) == item['sha256'] and zlib.crc32(padded) == checksum
    rollback = os.pread(fd,14876672,65536*512)
    assert sha(rollback) == '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
finally:
    os.close(fd)
mirrors = {'Image':'6c2b8b6492a26c1f8783d0503314b8700535ed690eea63476a09dab38a769ce5',
           'board.dtb':'a2721370964d3eb1f80a4b3a46be562852578e3055e3ff4169e2563852d0b791',
           'initramfs.cpio.gz':'783d3b9d11f4f59606ac50e4cb0c36ac7ca6ac3d05d227202624cc05bcbe397c'}
for folder in ('/boot','/home/debian/current-bundle'):
    for name,digest in mirrors.items():
        assert sha(Path(folder,name).read_bytes()) == digest,(folder,name)
for name in ('/boot/kernel.config','/boot/config-7.3.3-tzx-a523-accel1'):
    assert sha(Path(name).read_bytes()) == 'ba01595843f6ca6b37f058a89fd9ec0db4cc0bb38031a1523be44cc6f54095f3'
assert not Path('/sys/module/tzx_sram_log').exists()
print('BL31_STREAM_SELECTED_BOOT_READ_ONLY_VERIFY_PASS',json.dumps({
    'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'selected_bundle_sha256':manifest['sha256'], 'rollback_slot_unchanged':True,
    'toc0_and_gpt_crc': 'PASS','mirrors':8,'firmware_writes':False}),flush=True)
