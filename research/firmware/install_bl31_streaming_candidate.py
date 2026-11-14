"""Pinned manual EL3 diagnostic, separate slot, verified #5 header rollback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import uuid
import zlib

parser = argparse.ArgumentParser()
actions = parser.add_mutually_exclusive_group()
actions.add_argument('--stage', action='store_true')
actions.add_argument('--activate', action='store_true')
actions.add_argument('--restore', action='store_true')
args = parser.parse_args()
assert os.geteuid() == 0 and os.uname().release == '7.3.3-tzx-a523-accel1'
assert '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/class/block/mmcblk0/size').read_text().strip() == '244318208'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
for name in ('panfrost', 'tzx_sram_log', 'tzx_cpu_stream_probe'):
    assert not Path('/sys/module', name).exists(), name
assert not Path('/var/lib/tzx/gpu-qualified').exists()
sha = lambda data: hashlib.sha256(data).hexdigest()
OLD_SHA = '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
NEW_SHA = '165f940df7bcd97bddce20ec927d53fe32bcf3581fadbd3c10c5404484671e8a'
OLD_BL31 = '4f86a989584fe1e1312264ce549ecbb81bdc5656a2307cdef525371b81ad371a'
NEW_BL31 = '573865c541b221a8c55dada09496de61ecc3d93eb7641b6713e0412db5e36579'
TOC_SHA = 'ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df'
OLD_MANIFEST = 'eb0a03a538878ba5ca615861d19aef4d977924e590106ab969313e3cec3c83ef'
folder = Path('/home/debian/bl31-streaming')
manifest_bytes = (folder/'linux-bundle.json').read_bytes()
manifest = json.loads(manifest_bytes)
bl31 = (folder/'bl31.bin').read_bytes()
assert len(bl31) == 41124 and sha(bl31) == NEW_BL31
assert (manifest['start_lba'], manifest['header_lba'], manifest['bytes'], manifest['sha256']) == (98304,4096,14880768,NEW_SHA)
assert manifest['changed_payloads'] == ['bl31.bin']
backup = Path('/root/tzx-recovery/bl31-streaming')
installed = Path('/home/debian/installed-bundle.json')
pins = {
    '/boot/Image': '6c2b8b6492a26c1f8783d0503314b8700535ed690eea63476a09dab38a769ce5',
    '/home/debian/current-bundle/Image': '6c2b8b6492a26c1f8783d0503314b8700535ed690eea63476a09dab38a769ce5',
    '/boot/board.dtb': 'a2721370964d3eb1f80a4b3a46be562852578e3055e3ff4169e2563852d0b791',
    '/home/debian/current-bundle/board.dtb': 'a2721370964d3eb1f80a4b3a46be562852578e3055e3ff4169e2563852d0b791',
    '/boot/initramfs.cpio.gz': '783d3b9d11f4f59606ac50e4cb0c36ac7ca6ac3d05d227202624cc05bcbe397c',
    '/home/debian/current-bundle/initramfs.cpio.gz': '783d3b9d11f4f59606ac50e4cb0c36ac7ca6ac3d05d227202624cc05bcbe397c',
    '/boot/kernel.config': 'ba01595843f6ca6b37f058a89fd9ec0db4cc0bb38031a1523be44cc6f54095f3',
    '/boot/config-7.3.3-tzx-a523-accel1': 'ba01595843f6ca6b37f058a89fd9ec0db4cc0bb38031a1523be44cc6f54095f3',
}
for name, digest in pins.items():
    assert sha(Path(name).read_bytes()) == digest, name

def atomic(path, data):
    assert not path.is_symlink(), path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.bl31-stream-new')
    with tmp.open('wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    tmp.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o600)
    tmp.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

fd = os.open('/dev/mmcblk0', (os.O_RDWR|os.O_SYNC) if any((args.stage,args.activate,args.restore)) else os.O_RDONLY)
try:
    toc = os.pread(fd, 40960, 256*512)
    assert sha(toc) == TOC_SHA
    gpt = os.pread(fd,512,512)
    assert gpt[:8] == b'EFI PART' and str(uuid.UUID(bytes_le=gpt[56:72])) == 'c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
    checked = bytearray(gpt)
    crc = struct.unpack_from('<I',checked,16)[0]
    struct.pack_into('<I',checked,16,0)
    assert zlib.crc32(checked[:struct.unpack_from('<I',checked,12)[0]]) == crc
    table_lba, entries, stride, crc = struct.unpack_from('<QIII',gpt,72)
    assert stride >= 128 and 0 < entries*stride <= 65536
    table = os.pread(fd,entries*stride,table_lba*512)
    assert zlib.crc32(table) == crc
    starts = [struct.unpack_from('<Q',table,n*stride+32)[0] for n in range(entries) if any(table[n*stride:n*stride+16])]
    assert min(starts) == 131072 and 98304+14880768//512 < min(starts)
    old = os.pread(fd,14876672,65536*512)
    assert sha(old) == OLD_SHA
    header = bytearray(512)
    header[:8] = b'A523BND1'
    struct.pack_into('<II',header,8,1,5)
    candidate = bytearray(512)
    for index, name in enumerate(('Image','board.dtb','initramfs.cpio.gz','linux-entry.bin','bl31.bin')):
        lba,length,address,crc,r1,r2 = struct.unpack_from('<6I',old,32+index*24)
        data = old[(lba-65536)*512:(lba-65536)*512+length]
        if name == 'bl31.bin':
            assert sha(data) == OLD_BL31
            data = bl31
        item = manifest['items'][index]
        assert item['file'] == name and item['bytes'] == len(data) and item['sha256'] == sha(data)
        target_lba = 98304+len(candidate)//512
        assert item['lba'] == target_lba and int(item['load_address'],16) == address
        padded = data+bytes(-len(data)%512)
        struct.pack_into('<6I',header,32+index*24,target_lba,len(data),address,zlib.crc32(padded),0,0)
        candidate.extend(padded)
    struct.pack_into('<I',header,16,zlib.crc32(header))
    candidate[:512] = header
    assert len(candidate) == 14880768 and sha(candidate) == NEW_SHA
    current = os.pread(fd,512,4096*512)
    assert current in (old[:512],header)
    assert sha(installed.read_bytes()) in (OLD_MANIFEST,sha(manifest_bytes))
    if not args.restore:
        assert current == old[:512] and sha(installed.read_bytes()) == OLD_MANIFEST
    if args.stage:
        prior = os.pread(fd,15020032,98304*512)
        assert sha(prior) == '606a18d4eeeee98ccdff67fca33911437380e79b970a504f2356ba99dec37116' or sha(prior[:len(candidate)]) == NEW_SHA
        backup.mkdir(parents=True,exist_ok=True)
        for name,data in {'active-header.bin':old[:512],'installed-bundle.json':installed.read_bytes(),
                          'installer.py':Path(__file__).read_bytes()}.items():
            p=backup/name
            if not p.exists(): atomic(p,data)
            assert p.read_bytes() == data
        cpufreq = subprocess.run(['systemctl','is-enabled','--quiet','tzx-cpufreq.service']).returncode == 0
        state = backup/'cpufreq-was-enabled.json'
        if not state.exists(): atomic(state,json.dumps(cpufreq).encode()+b'\n')
        assert os.pwrite(fd,candidate,98304*512) == len(candidate)
        os.fsync(fd)
        assert sha(os.pread(fd,len(candidate),98304*512)) == NEW_SHA
        print('BL31_STREAM_STAGED_FULL_READBACK_PASS',NEW_SHA,flush=True)
    if args.activate or args.restore:
        assert (backup/'active-header.bin').read_bytes() == old[:512]
        assert sha((backup/'installed-bundle.json').read_bytes()) == OLD_MANIFEST
        if args.activate:
            assert sha(os.pread(fd,len(candidate),98304*512)) == NEW_SHA
            subprocess.run(['systemctl','disable','--now','tzx-cpufreq.service'],check=True,timeout=45)
            assert not Path('/sys/module/tzx_cpufreq_divider').exists()
            target,base = candidate,98304
            atomic(installed,manifest_bytes)
        else:
            target,base = old,65536
            atomic(installed,(backup/'installed-bundle.json').read_bytes())
            if json.loads((backup/'cpufreq-was-enabled.json').read_text()):
                subprocess.run(['systemctl','enable','tzx-cpufreq.service'],check=True,timeout=20)
        assert os.pwrite(fd,target[:512],4096*512) == 512
        os.fsync(fd)
        assert os.pread(fd,512,4096*512) == target[:512]
        for index in range(5):
            lba,length,*_ = struct.unpack_from('<6I',target,32+24*index)
            count=(length+511)&~511
            assert os.pread(fd,count,lba*512) == target[(lba-base)*512:(lba-base)*512+count]
        print('BL31_STREAM_SELECTED_FULL_PAYLOAD_READBACK_PASS',base,flush=True)
    assert sha(os.pread(fd,14876672,65536*512)) == OLD_SHA
    assert os.pread(fd,40960,256*512) == toc
    assert os.pread(fd,512,512) == gpt and os.pread(fd,len(table),table_lba*512) == table
finally:
    os.close(fd)
print('BL31_STREAM_INSTALL_CHECK_PASS',json.dumps({'stage':args.stage,'activate':args.activate,'restore':args.restore,
      'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'kernel_changed':False}),flush=True)
os.sync()
if args.activate or args.restore:
    subprocess.run(['systemd-run','--unit=tzx-bl31-stream-'+('restore' if args.restore else 'activate')+'-reboot',
                    '--on-active=3s','/usr/bin/systemctl','reboot'],check=True,timeout=20)
