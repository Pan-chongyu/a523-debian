#!/usr/bin/env python3
"""Compose a compact complete eMMC image; expand GPT/ext4 while flashing/booting."""
import argparse,gzip,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flasher.core import make_gpt,sha_file

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--assets',type=Path,required=True);args=parser.parse_args()
    assets=args.assets;root=args.root;image=assets/'a523-debian-13-xfce-20261114.img'
    size=5*1024**3;sectors=size//512
    assert not image.exists()
    root_image=assets/'rootfs.ext4';root_bytes=size-1179648*512-33*512
    with root_image.open('wb') as stream:stream.truncate(root_bytes)
    subprocess.run(['mkfs.ext4','-q','-F','-L','DEBIAN_ROOT','-E','lazy_itable_init=0,lazy_journal_init=0',
                    '-d',str(root),str(root_image)],check=True)
    result=subprocess.run(['e2fsck','-fn',str(root_image)])
    assert result.returncode==0
    fat=assets/'boot.fat'
    with fat.open('wb') as stream:stream.truncate(512*1024**2)
    subprocess.run(['mkfs.vfat','-F32','-n','DEBIAN_BOOT',str(fat)],check=True)
    for name in ('Image','board.dtb','initramfs.cpio.gz'):
        subprocess.run(['mcopy','-o','-i',str(fat),str(assets/name),'::'+name],check=True)
    for path in (root/'boot').glob('config-*'):
        subprocess.run(['mcopy','-o','-i',str(fat),str(path),'::'+path.name],check=True)
    subprocess.run(['fsck.vfat','-n',str(fat)],check=True)
    primary,secondary=make_gpt(sectors)
    with image.open('wb') as stream:
        stream.truncate(size)
        for offset,data in ((0,primary),((sectors-33)*512,secondary),
             (256*512,(assets/'toc0.bin').read_bytes()),(4096*512,(assets/'header.bin').read_bytes()),
             (49152*512,(assets/'logo.bin').read_bytes()),(98304*512,(assets/'active-bundle.bin').read_bytes())):
            stream.seek(offset);stream.write(data)
        # A fallback bundle at65536 may overlap a larger active bundle if
        # payloads grow. This layout keeps only one selected public bundle;
        # FEL always provides the independent recovery transport.
        stream.seek(131072*512)
        def sparse_copy(source):
            for data in iter(lambda:source.read(4*1024*1024),b''):
                if data.count(0)==len(data):stream.seek(len(data),1)
                else:stream.write(data)
        with fat.open('rb') as source:sparse_copy(source)
        stream.seek(1179648*512)
        with root_image.open('rb') as source:sparse_copy(source)
        stream.flush();os.fsync(stream.fileno())
    # The image now contains the checked filesystems. Reclaim temporary
    # filesystem copies before compression on hosts with limited disk space.
    root_image.unlink();fat.unlink()
    target=image.with_suffix('.img.gz')
    with image.open('rb') as source,target.open('wb') as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',compresslevel=6,mtime=0) as output:
        shutil.copyfileobj(source,output,4*1024*1024)
    files={}
    for key,path in (('image',target),('toc0',assets/'toc0.bin'),('helper',assets/'fel-emmc.bin'),
        ('installer',assets/'installer-bundle.bin'),('installer_header',assets/'installer-header.bin')):
        files[key]=dict(name=path.name,bytes=path.stat().st_size,sha256=sha_file(path))
    m=dict(format='a523-debian-release-v1',version='v0.1.0-20261114',
        board_profile='tzx-p30a523-20t5g-lpddr3-4g-uem128',emmc_sectors=244318208,
        files=files,image_uncompressed_bytes=size,image_uncompressed_sha256=sha_file(image),
        status='experimental-prerelease',public_image_full_hardware_reflash_tested=False,
        original_board_runtime_tested=True,default_credentials='debian / debian',ssh_enabled=False)
    (assets/'release-manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    (assets/'SHA256SUMS').write_text(''.join(item['sha256']+'  '+item['name']+'\n' for item in files.values()))
    print('COMPLETE_PUBLIC_IMAGE_BUILT',json.dumps(m),flush=True)

if __name__=='__main__':main()
