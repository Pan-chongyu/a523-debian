#!/usr/bin/env python3
"""Build the public board profile from its exact qualified boot template.

Only the SRAM CID comparison becomes a manufacturer/product-prefix match.
Board markings, capacity and DRAM remain a manual and host-side requirement.
"""
import argparse,hashlib,json,struct,subprocess,zlib
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

SHA=lambda data:hashlib.sha256(data).hexdigest()

def public_toc0(original,key_path):
    assert SHA(original)=='fc208e752fc816e1e016944cd0f4c4d9497989ec174718e5f3b12d030136b0ca'
    data=bytearray(original);changes=[]
    # CID response is low-word first. Compare/store only words2 and3,
    # containing the first eight CID bytes (manufacturer/product family).
    # Emulated with changed serial numbers and rejected product prefixes.
    for address,old,new in ((0x44c98,0xe28dc010,0xe28dc018),
                            (0x44ca0,0xe88c000f,0xe88c000c),
                            (0x44cac,0xe1a0300d,0xe28d3008),
                            (0x44ce8,0x0002df00,0x0002df08)):
        offset=0xf80+address-0x44000
        assert struct.unpack_from('<I',data,offset)[0]==old
        struct.pack_into('<I',data,offset,new)
        changes.append(dict(address=hex(address),old=hex(old),new=hex(new)))
    cert=bytearray(data[0xc80:0xf80]);firmware=bytes(data[0xf80:0xf80+43712])
    if key_path.exists():key=serialization.load_pem_private_key(key_path.read_bytes(),password=None)
    else:
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        key_path.parent.mkdir(parents=True,exist_ok=True)
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()));key_path.chmod(0o600)
    numbers=key.private_numbers();cert[178:434]=numbers.public_numbers.n.to_bytes(256,'big')
    cert[445:477]=hashlib.sha256(firmware).digest()
    cert[-256:]=pow(int.from_bytes(hashlib.sha256(cert[4:487]).digest(),'big'),numbers.d,numbers.public_numbers.n).to_bytes(256,'big')
    data[0xc80:0xf80]=cert;struct.pack_into('<I',data,12,0x5f0a6c39)
    struct.pack_into('<I',data,12,sum(struct.unpack('<12288I',data))&0xffffffff)
    assert pow(int.from_bytes(cert[-256:],'big'),65537,numbers.public_numbers.n)==int.from_bytes(hashlib.sha256(cert[4:487]).digest(),'big')
    return bytes(data),changes

def bundle(items,start_lba=98304):
    header=bytearray(512);header[:8]=b'A523BND1'
    struct.pack_into('<II',header,8,1,5)
    body=bytearray();manifest=[]
    for index,(name,address,content) in enumerate(items):
        lba=start_lba+1+len(body)//512;rounded=content+bytes(-len(content)%512)
        struct.pack_into('<6I',header,32+index*24,lba,len(content),address,zlib.crc32(rounded),0,0)
        body.extend(rounded)
        manifest.append(dict(file=name,lba=lba,bytes=len(content),load_address=hex(address),sha256=SHA(content)))
    struct.pack_into('<I',header,16,zlib.crc32(header))
    assert len(header)+len(body)<(131072-start_lba)*512
    return bytes(header+body),manifest

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--kernel',type=Path,required=True);parser.add_argument('--initramfs',type=Path,required=True)
    parser.add_argument('--installer-initramfs',type=Path,required=True);parser.add_argument('--key',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    original=(args.input/'active-bundle.bin').read_bytes()
    items=[]
    for index,name in enumerate(('Image','board.dtb','initramfs.cpio.gz','linux-entry.bin','bl31.bin')):
        lba,size,address,crc,_,_=struct.unpack_from('<6I',original,32+index*24)
        offset=(lba-98304)*512;content=original[offset:offset+size]
        assert zlib.crc32(original[offset:offset+((size+511)&~511)])==crc
        if index==0:content=args.kernel.read_bytes()
        if index==2:content=args.initramfs.read_bytes()
        # linux_entry has a constant copy size. Preserve exact kernel length
        # until a rebuilt entry stub is supplied by the build pipeline.
        if index==3 and (args.out/'linux-entry.bin').exists():content=(args.out/'linux-entry.bin').read_bytes()
        items.append((name,address,content))
    active,entries=bundle(items)
    def update_dtb(entries,initrd):
        temporary=args.out/'board.dtb';temporary.write_bytes(entries[1][2])
        subprocess.run(['fdtput','-t','x',str(temporary),'/chosen','linux,initrd-end','0',hex(0x60000000+len(initrd))[2:]],check=True)
        entries[1]=('board.dtb',entries[1][1],temporary.read_bytes())
    update_dtb(items,args.initramfs.read_bytes())
    active,entries=bundle(items)
    installer_items=list(items);installer_items[2]=('initramfs.cpio.gz',0x60000000,args.installer_initramfs.read_bytes())
    update_dtb(installer_items,args.installer_initramfs.read_bytes())
    installer,installer_entries=bundle(installer_items)
    (args.out/'board.dtb').write_bytes(items[1][2])
    toc,patches=public_toc0((args.input/'toc0.bin').read_bytes(),args.key)
    for name,data in (('toc0.bin',toc),('active-bundle.bin',active),('header.bin',active[:512]),
                      ('installer-bundle.bin',installer),('installer-header.bin',installer[:512]),
                      ('logo.bin',(args.input/'logo.bin').read_bytes())):
        (args.out/name).write_bytes(data)
    m=dict(toc0_sha256=SHA(toc),toc0_bytes=len(toc),toc0_patches=patches,boot_profile='model-prefix-and-exact-capacity',
        active_bundle_sha256=SHA(active),header_sha256=SHA(active[:512]),kernel_sha256=SHA(args.kernel.read_bytes()),
        items=entries,installer_items=installer_entries,hardware_boot_of_public_variant_verified=False)
    (args.out/'boot-build.json').write_text(json.dumps(m,indent=2)+'\n')
    print('PUBLIC_BOOT_PROFILE_BUILT',json.dumps(m),flush=True)

if __name__=='__main__':main()
