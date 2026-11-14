"""Pinned one-CPU diagnostic in the spare boot slot, with intact #5 rollback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import uuid
import zlib

parser=argparse.ArgumentParser()
group=parser.add_mutually_exclusive_group()
group.add_argument('--stage',action='store_true')
group.add_argument('--activate',action='store_true')
group.add_argument('--restore',action='store_true')
args=parser.parse_args()
assert os.geteuid()==0 and os.uname().release=='7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
assert Path('/sys/class/block/mmcblk0/size').read_text().strip()=='244318208'
assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
for name in ('panfrost','tzx_sram_log','tzx_cpu_stream_probe'):
    assert not Path('/sys/module',name).exists(),name
assert not Path('/var/lib/tzx/gpu-qualified').exists()
sha=lambda data:hashlib.sha256(data).hexdigest()
OLD='3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
NEW='c07fa1ff67b73f637d7213599f1e9b727c5ec3a6b9bc7b5dca718bdbbf0c9cbd'
OLD_MANIFEST='eb0a03a538878ba5ca615861d19aef4d977924e590106ab969313e3cec3c83ef'
TOC='ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df'
folder=Path('/home/debian/single-cpu-trial')
manifest_bytes=(folder/'linux-bundle.json').read_bytes()
manifest=json.loads(manifest_bytes)
dtb=(folder/'board.dtb').read_bytes()
assert (manifest['start_lba'],manifest['header_lba'],manifest['bytes'],manifest['sha256'])==(98304,4096,14875648,NEW)
assert sha(dtb)=='59c8dc5ec6be26ba190774e15992af39c249b400353d4c567ef462694f7e3205'
assert manifest['changed_payloads']==['board.dtb']
assert manifest['bootargs_after']==manifest['bootargs_before']+' maxcpus=1'
installed=Path('/home/debian/installed-bundle.json')
backup=Path('/root/tzx-recovery/single-cpu-trial')
mirror_names=('/boot/board.dtb','/home/debian/current-bundle/board.dtb')

def atomic(path,data):
    assert not path.is_symlink()
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.singlecpu-new')
    with tmp.open('wb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())
    tmp.chmod(path.stat().st_mode&0o777 if path.exists() else 0o600)
    tmp.replace(path)
    fd=os.open(path.parent,os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

fd=os.open('/dev/mmcblk0',os.O_RDWR|os.O_SYNC if any((args.stage,args.activate,args.restore)) else os.O_RDONLY)
try:
    toc=os.pread(fd,40960,256*512)
    assert sha(toc)==TOC
    gpt=os.pread(fd,512,512)
    assert gpt[:8]==b'EFI PART' and str(uuid.UUID(bytes_le=gpt[56:72]))=='c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
    checked=bytearray(gpt);crc=struct.unpack_from('<I',checked,16)[0];struct.pack_into('<I',checked,16,0)
    assert zlib.crc32(checked[:struct.unpack_from('<I',checked,12)[0]])==crc
    table_lba,count,stride,crc=struct.unpack_from('<QIII',gpt,72)
    assert stride>=128 and 0<count*stride<=65536
    table=os.pread(fd,count*stride,table_lba*512)
    assert zlib.crc32(table)==crc
    starts=[struct.unpack_from('<Q',table,i*stride+32)[0] for i in range(count) if any(table[i*stride:i*stride+16])]
    assert min(starts)==131072 and 98304+14875648//512<min(starts)
    old=os.pread(fd,14876672,65536*512)
    assert sha(old)==OLD
    header=bytearray(512);header[:8]=b'A523BND1';struct.pack_into('<II',header,8,1,5)
    candidate=bytearray(512)
    old_dtb=None
    for i,item in enumerate(manifest['items']):
        lba,length,address,checksum,r1,r2=struct.unpack_from('<6I',old,32+i*24)
        payload=old[(lba-65536)*512:(lba-65536)*512+length]
        if i==1:
            old_dtb=payload
            assert sha(old_dtb)=='a2721370964d3eb1f80a4b3a46be562852578e3055e3ff4169e2563852d0b791'
            payload=dtb
        assert (item['bytes'],item['sha256'],int(item['load_address'],16))==(len(payload),sha(payload),address)
        dest=98304+len(candidate)//512
        assert item['lba']==dest
        block=payload+bytes(-len(payload)%512)
        struct.pack_into('<6I',header,32+i*24,dest,len(payload),address,zlib.crc32(block),0,0)
        candidate.extend(block)
        if i in (0,2):
            for parent in ('/boot','/home/debian/current-bundle'):
                assert sha(Path(parent,item['file']).read_bytes())==sha(payload)
    struct.pack_into('<I',header,16,zlib.crc32(header));candidate[:512]=header
    assert len(candidate)==14875648 and sha(candidate)==NEW
    current=os.pread(fd,512,4096*512)
    assert current in (old[:512],header)
    assert sha(installed.read_bytes()) in (OLD_MANIFEST,sha(manifest_bytes))
    for name in mirror_names:
        assert Path(name).read_bytes() in (old_dtb,dtb),name
    if not args.restore:
        assert current==old[:512] and sha(installed.read_bytes())==OLD_MANIFEST
        assert Path('/sys/devices/system/cpu/online').read_text().strip()=='0-7'
    if args.stage:
        prior=os.pread(fd,14880768,98304*512)
        assert sha(prior)=='165f940df7bcd97bddce20ec927d53fe32bcf3581fadbd3c10c5404484671e8a' or sha(prior[:len(candidate)])==NEW
        backup.mkdir(parents=True,exist_ok=True)
        files={'active-header.bin':old[:512],'installed-bundle.json':installed.read_bytes(),'board.dtb':old_dtb}
        for name,data in files.items():
            target=backup/name
            if not target.exists():atomic(target,data)
            assert target.read_bytes()==data
        state=backup/'cpufreq-was-enabled.json'
        if not state.exists():
            enabled=subprocess.run(['systemctl','is-enabled','--quiet','tzx-cpufreq']).returncode==0
            atomic(state,json.dumps(enabled).encode()+b'\n')
        assert os.pwrite(fd,candidate,98304*512)==len(candidate)
        os.fsync(fd)
        assert sha(os.pread(fd,len(candidate),98304*512))==NEW
        print('SINGLE_CPU_STAGED_FULL_READBACK_PASS',NEW,flush=True)
    if args.activate or args.restore:
        assert (backup/'active-header.bin').read_bytes()==old[:512]
        assert sha((backup/'installed-bundle.json').read_bytes())==OLD_MANIFEST
        assert (backup/'board.dtb').read_bytes()==old_dtb
        if args.activate:
            assert sha(os.pread(fd,len(candidate),98304*512))==NEW
            subprocess.run(['systemctl','disable','--now','tzx-cpufreq'],check=True,timeout=45)
            target,base,mirror=candidate,98304,dtb
            atomic(installed,manifest_bytes)
        else:
            target,base,mirror=old,65536,old_dtb
            atomic(installed,(backup/'installed-bundle.json').read_bytes())
            if json.loads((backup/'cpufreq-was-enabled.json').read_text()):
                subprocess.run(['systemctl','enable','tzx-cpufreq'],check=True,timeout=20)
        for name in mirror_names:atomic(Path(name),mirror)
        assert os.pwrite(fd,target[:512],4096*512)==512
        os.fsync(fd)
        assert os.pread(fd,512,4096*512)==target[:512]
        for i in range(5):
            lba,length,*_=struct.unpack_from('<6I',target,32+i*24)
            size=(length+511)&~511
            assert os.pread(fd,size,lba*512)==target[(lba-base)*512:(lba-base)*512+size]
        print('SINGLE_CPU_SELECTED_FULL_PAYLOAD_READBACK_PASS',base,flush=True)
    assert sha(os.pread(fd,14876672,65536*512))==OLD
    assert os.pread(fd,40960,256*512)==toc
    assert os.pread(fd,512,512)==gpt and os.pread(fd,len(table),table_lba*512)==table
finally:
    os.close(fd)
print('SINGLE_CPU_INSTALL_VERIFY_PASS',json.dumps(vars(args)),flush=True)
os.sync()
if args.activate or args.restore:
    subprocess.run(['systemd-run','--unit=tzx-single-cpu-'+('restore' if args.restore else 'activate')+'-reboot',
                    '--on-active=3s','/usr/bin/systemctl','reboot'],check=True,timeout=20)
