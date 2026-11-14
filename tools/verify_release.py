#!/usr/bin/env python3
"""Read-only validation of release files, boot regions and filesystem headers."""
import argparse,gzip,hashlib,json,struct,zlib
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flasher.core import validate_manifest,verify_asset,verify_gpt,sha_file

def verify_bundle(data):
    assert data[:8]==b'A523BND1'
    header=bytearray(data[:512]);expected=struct.unpack_from('<I',header,16)[0]
    struct.pack_into('<I',header,16,0);assert zlib.crc32(header)==expected
    for i in range(5):
        lba,size,address,checksum,_,_=struct.unpack_from('<6I',data,32+i*24)
        offset=(lba-98304)*512;rounded=(size+511)&~511
        assert len(data[offset:offset+rounded])==rounded and zlib.crc32(data[offset:offset+rounded])==checksum

def main():
    p=argparse.ArgumentParser();p.add_argument('assets',type=Path);args=p.parse_args();assets=args.assets
    manifest=validate_manifest(json.loads((assets/'release-manifest.json').read_text()))
    for item in manifest['files'].values():verify_asset(assets/item['name'],item)
    toc=(assets/'toc0.bin').read_bytes();checksum=struct.unpack_from('<I',toc,12)[0]
    assert (sum(struct.unpack('<%dI'%(len(toc)//4),toc))+0x5f0a6c39-2*checksum)&0xffffffff==0
    cert=toc[0xc80:0xf80];size=struct.unpack_from('<I',toc,0x58)[0]
    assert hashlib.sha256(toc[0xf80:0xf80+size]).digest()==cert[445:477]
    n=int.from_bytes(cert[178:434],'big');e=int.from_bytes(cert[436:439],'big')
    assert pow(int.from_bytes(cert[-256:],'big'),e,n)==int.from_bytes(hashlib.sha256(cert[4:487]).digest(),'big')
    verify_bundle((assets/'installer-bundle.bin').read_bytes())
    image=assets/'a523-debian-13-xfce-20261114.img'
    assert image.stat().st_size==manifest['image_uncompressed_bytes']
    assert sha_file(image)==manifest['image_uncompressed_sha256']
    with image.open('rb') as stream:
        verify_gpt(stream.read(34*512));stream.seek(-512,2);backup=bytearray(stream.read(512))
        expected=struct.unpack_from('<I',backup,16)[0];struct.pack_into('<I',backup,16,0)
        assert zlib.crc32(backup[:92])==expected
        for name,lba in (('toc0.bin',256),('header.bin',4096),('logo.bin',49152),('active-bundle.bin',98304)):
            content=(assets/name).read_bytes();stream.seek(lba*512);assert stream.read(len(content))==content
        stream.seek(1179648*512+1024);superblock=stream.read(1024)
        assert superblock[56:58]==b'\x53\xef' and superblock[120:136].rstrip(b'\0')==b'DEBIAN_ROOT'
        stream.seek(131072*512);fat=stream.read(512);assert fat[82:90]==b'FAT32   ' and fat[71:82]==b'DEBIAN_BOOT'
    verify_bundle((assets/'active-bundle.bin').read_bytes())
    digest=hashlib.sha256();count=0
    with gzip.open(assets/manifest['files']['image']['name'],'rb') as source:
        for block in iter(lambda:source.read(4*1024*1024),b''):digest.update(block);count+=len(block)
    assert count==manifest['image_uncompressed_bytes'] and digest.hexdigest()==manifest['image_uncompressed_sha256']
    report=dict(release=manifest['version'],automated_checks=dict(asset_hashes='PASS',toc0_checksum='PASS',
        toc0_firmware_hash='PASS',toc0_rsa_signature='PASS',installer_bundle_crc='PASS',active_bundle_crc='PASS',
        primary_and_backup_gpt='PASS',boot_regions='PASS',filesystem_headers='PASS',
        raw_and_decompressed_image_digest='PASS'),
        public_image_full_hardware_reflash_tested=False,
        qualification_scope='Original-unit observations plus automated release checks; no full public-image hardware flash')
    (assets/'image-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print('RELEASE_IMAGE_VALIDATION_PASS',json.dumps(report),flush=True)

if __name__=='__main__':main()
