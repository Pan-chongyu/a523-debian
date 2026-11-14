"""Verified streaming writes and GPT resizing; independent of USB discovery."""
import gzip,hashlib,json,os,struct,uuid,zlib
from pathlib import Path,PurePosixPath

BLOCK=4*1024*1024
COMMIT_BYTES=BLOCK

def sha_file(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(BLOCK),b''):digest.update(data)
    return digest.hexdigest()

def validate_manifest(value):
    if value.get('format')!='a523-debian-release-v1':raise ValueError('Unknown release format')
    if value.get('board_profile')!='tzx-p30a523-20t5g-lpddr3-4g-uem128':raise ValueError('Wrong board profile')
    if value.get('emmc_sectors')!=244318208:raise ValueError('Wrong eMMC capacity profile')
    for item in value['files'].values():
        name=PurePosixPath(item['name'])
        if name.name!=item['name'] or '..' in name.parts or name.is_absolute():raise ValueError('Unsafe asset path')
        if not isinstance(item['bytes'],int) or item['bytes']<=0:raise ValueError('Invalid size')
        if len(item['sha256'])!=64 or any(c not in '0123456789abcdef' for c in item['sha256']):raise ValueError('Invalid digest')
    return value

def verify_asset(path,item):
    if Path(path).stat().st_size!=item['bytes'] or sha_file(path)!=item['sha256']:
        raise ValueError('Asset checksum mismatch: '+item['name'])

def make_gpt(sectors,root_end=None):
    if sectors<4194304:raise ValueError('Image/device too small')
    last=sectors-1;root_end=last-33 if root_end is None else root_end
    if not 1179648<root_end<=last-33:raise ValueError('Invalid root boundary')
    table=bytearray(128*128)
    for index,(name,start,end,type_id,partition_id) in enumerate((
        ('DEBIAN_BOOT',131072,1179647,'EBD0A0A2-B9E5-4433-87C0-68B6B72699C7','71c7a431-39c3-4ca8-b82f-7464309b61f1'),
        ('DEBIAN_ROOT',1179648,root_end,'0FC63DAF-8483-4772-8E79-3D69D8477DE4','ae5dfab4-c7c8-44f9-960a-40af7926ba58'))):
        offset=index*128;table[offset:offset+16]=uuid.UUID(type_id).bytes_le
        table[offset+16:offset+32]=uuid.UUID(partition_id).bytes_le
        struct.pack_into('<QQQ',table,offset+32,start,end,0)
        table[offset+56:offset+56+len(name)*2]=name.encode('utf-16-le')
    def header(current,backup,entries_lba):
        data=bytearray(512);data[:8]=b'EFI PART'
        struct.pack_into('<IIIIQQQQ',data,8,0x10000,92,0,0,current,backup,34,last-33)
        data[56:72]=uuid.UUID('c9a3ed89-a30d-4fbc-ba53-208fa8617cbc').bytes_le
        struct.pack_into('<QIII',data,72,entries_lba,128,128,zlib.crc32(table))
        struct.pack_into('<I',data,16,zlib.crc32(data[:92]));return bytes(data)
    mbr=bytearray(512);mbr[446+4]=0xee
    struct.pack_into('<II',mbr,446+8,1,min(last,0xffffffff));mbr[510:512]=b'\x55\xaa'
    return bytes(mbr)+header(1,last,2)+bytes(table),bytes(table)+header(last,1,last-32)

def checked_write(stream,offset,data):
    stream.seek(offset)
    if stream.write(data)!=len(data):raise IOError('Short write at '+str(offset))
    stream.flush();os.fsync(stream.fileno());stream.seek(offset)
    if stream.read(len(data))!=data:raise IOError('Readback mismatch at '+str(offset))

def flash_image(image,target,manifest,sectors,progress=lambda done,total:None):
    """No discovery: caller has verified FEL identity, session nonce and consent.

    Defer first4MiB (GPT, nonce, TOC0 and header) until all other data passes
    readback. No user-data backup. The remainder of a larger device is not a
    secure erase; GPT extends root and initramfs grows ext4 on first boot.
    """
    if sectors!=manifest['emmc_sectors']:raise ValueError('Target capacity changed')
    image_info=manifest['files']['image'];verify_asset(image,image_info)
    total=manifest['image_uncompressed_bytes']
    if total%512 or total>sectors*512:raise ValueError('Image exceeds target')
    original=gzip.open(image,'rb');digest=hashlib.sha256();offset=0
    with original,open(target,'r+b',buffering=0) as stream:
        deferred=original.read(COMMIT_BYTES)
        if len(deferred)!=COMMIT_BYTES:raise ValueError('Truncated image prefix')
        digest.update(deferred);offset=len(deferred)
        while offset<total:
            data=original.read(min(BLOCK,total-offset))
            if not data:raise ValueError('Truncated image')
            digest.update(data);checked_write(stream,offset,data);offset+=len(data);progress(offset,total)
        if original.read(1):raise ValueError('Image has unexpected trailing data')
        if digest.hexdigest()!=manifest['image_uncompressed_sha256']:raise ValueError('Uncompressed image checksum mismatch')
        primary,secondary=make_gpt(sectors)
        checked_write(stream,(sectors-33)*512,secondary)
        # Old image backup GPT lies inside the expanded root partition. Clear
        # it only after verified data, before selecting the final boot chain.
        if total<sectors*512:checked_write(stream,total-33*512,bytes(33*512))
        deferred=primary+deferred[len(primary):]
        checked_write(stream,0,deferred)
    progress(total,total)

def verify_gpt(data):
    header=bytearray(data[512:1024]);length,checksum=struct.unpack_from('<II',header,12)
    if header[:8]!=b'EFI PART' or length!=92:raise ValueError('Bad GPT header')
    struct.pack_into('<I',header,16,0)
    if zlib.crc32(header[:length])!=checksum:raise ValueError('Bad GPT CRC')
    if zlib.crc32(data[1024:34*512])!=struct.unpack_from('<I',header,88)[0]:raise ValueError('Bad table CRC')
    return True
