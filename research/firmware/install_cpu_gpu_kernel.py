"""Select a pinned scheduler/GPU-cooling kernel, retaining an intact boot slot."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import uuid
import zlib

assert len(sys.argv)==3 and sys.argv[1] in ('install','verify-boot','restore')
operation,pin=sys.argv[1:]
assert re.fullmatch('[0-9a-f]{64}',pin) and os.geteuid()==0
assert os.uname().release=='7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
assert Path('/sys/class/block/mmcblk0/size').read_text().strip()=='244318208'
assert Path('/sys/devices/system/cpu/online').read_text().strip()=='0-7'
assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
sha=lambda b:hashlib.sha256(b).hexdigest()
folder=Path('/home/debian/cpu-gpu-kernel')
backup=Path('/root/tzx-recovery/cpu-gpu-kernel')
state_path=Path('/var/lib/tzx/cpu-gpu-kernel-installed.json')
manifest_data=(folder/'linux-bundle.json').read_bytes()
assert sha(manifest_data)==pin
manifest=json.loads(manifest_data)
candidate=(folder/'linux-bundle.bin').read_bytes()
config=(folder/'kernel.config').read_bytes()
panfrost=(folder/'panfrost.ko').read_bytes()
assert sha(candidate)==manifest['sha256'] and len(candidate)==manifest['bytes']
assert sha(config)==manifest['config_sha256'] and sha(panfrost)==manifest['panfrost_sha256']
assert manifest['config_changes']==['SCHED_MC','DEVFREQ_THERMAL']
assert (manifest['start_lba'],manifest['header_lba'])==(98304,4096)
assert 98304+len(candidate)//512<131072
OLD='2792b0e8b1087287c4e1da8f036fb3a72b11d4b5e21da7e38111d90785a6509e'
FALLBACK='091ebfe06aa47ca3a4ac7e347838dd6175c575771032e1703e6b7b1480e460e3'
OLD_CONFIG='59cc725631e95f3726080322e19f4868ef461035e85d6f7dd02b5be2915aced6'
OLD_PANFROST='ad4127adbd990361f89dfa65e3707927609f7eefedc766cd03dedb25f6ba97ae'
TOC='311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75'
BOOT=Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def run(*args,timeout=65):
    return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=timeout)


def atomic(path,data,mode=None):
    assert not path.is_symlink()
    if mode is None:mode=path.stat().st_mode&0o777 if path.exists() else 0o600
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.cpu-gpu-new')
    with temp.open('wb') as f:
        f.write(data);os.fchmod(f.fileno(),mode);f.flush();os.fsync(f.fileno())
    temp.replace(path)
    d=os.open(path.parent,os.O_DIRECTORY);os.fsync(d);os.close(d)


def record(path,value):atomic(path,(json.dumps(value,indent=2)+'\n').encode())


def parts(bundle,start):
    assert bundle[:8]==b'A523BND1' and struct.unpack_from('<II',bundle,8)==(1,5)
    h=bytearray(bundle[:512]);crc=struct.unpack_from('<I',h,16)[0];struct.pack_into('<I',h,16,0)
    assert zlib.crc32(h)==crc
    result=[]
    for i in range(5):
        lba,n,address,crc,r1,r2=struct.unpack_from('<6I',bundle,32+i*24)
        off=(lba-start)*512;padded=bundle[off:off+((n+511)&~511)]
        assert off>=512 and len(padded)==((n+511)&~511) and zlib.crc32(padded)==crc and not(r1 or r2)
        result.append((lba,n,address,padded[:n]))
    return result


fd=os.open('/dev/mmcblk0',os.O_RDONLY if operation=='verify-boot' else os.O_RDWR|os.O_SYNC)
try:
    primary=os.pread(fd,34*512,0);secondary=os.pread(fd,33*512,(244318208-33)*512)
    gpt=bytearray(primary[512:1024]);assert gpt[:8]==b'EFI PART'
    assert str(uuid.UUID(bytes_le=bytes(gpt[56:72])))=='c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
    crc=struct.unpack_from('<I',gpt,16)[0];struct.pack_into('<I',gpt,16,0)
    assert zlib.crc32(gpt[:struct.unpack_from('<I',gpt,12)[0]])==crc
    lba,count,stride,crc=struct.unpack_from('<QIII',gpt,72)
    assert 0<count*stride<=65536
    table=os.pread(fd,count*stride,lba*512);assert zlib.crc32(table)==crc
    assert min(struct.unpack_from('<Q',table,i*stride+32)[0] for i in range(count) if any(table[i*stride:i*stride+16]))==131072
    toc=os.pread(fd,40960,256*512);assert sha(toc)==TOC
    fallback=os.pread(fd,15008768,65536*512);assert sha(fallback)==FALLBACK
    fallback_parts=parts(fallback,65536);new_parts=parts(candidate,98304)
    for i,(item,part) in enumerate(zip(manifest['items'],new_parts)):
        assert (item['lba'],item['bytes'],int(item['load_address'],16),item['sha256'])==(*part[:3],sha(part[3]))
        assert part[2]==fallback_parts[i][2]
        if i in (1,2,4):assert part[3]==fallback_parts[i][3]
    if operation=='install':
        assert not backup.exists() and not state_path.exists()
        old=os.pread(fd,15008768,98304*512);assert sha(old)==OLD
        active=os.pread(fd,512,4096*512);assert active==old[:512]
        current=gzip.decompress(Path('/proc/config.gz').read_bytes());assert sha(current)==OLD_CONFIG
        assert set(config.decode().splitlines())-set(current.decode().splitlines())=={'CONFIG_SCHED_MC=y','CONFIG_DEVFREQ_THERMAL=y'}
        assert set(current.decode().splitlines())-set(config.decode().splitlines())=={'# CONFIG_SCHED_MC is not set','# CONFIG_DEVFREQ_THERMAL is not set'}
        assert 'tzx_dma32' in run('modinfo','-p',str(folder/'panfrost.ko'))
        assert b'devfreq_cooling_em_register' in panfrost
        run('python3','/usr/local/lib/tzx-dram-gpu/runtime.py','guard')
        run('systemctl','stop','tzx-emmc-hs.service')
        mirrors={'/home/debian/installed-bundle.json':manifest_data,
            '/boot/kernel.config':config,'/boot/config-7.3.3-tzx-a523-accel1':config,
            '/usr/local/lib/tzx-dram-gpu/panfrost.ko':panfrost}
        for item,part in zip(manifest['items'][:3],new_parts[:3]):
            for parent in ('/boot','/home/debian/current-bundle'):
                mirrors[str(Path(parent)/item['file'])]=part[3]
        runtime=Path('/usr/local/lib/tzx-dram-gpu/runtime.py').read_bytes()
        assert runtime.count(OLD_PANFROST.encode())==1
        mirrors['/usr/local/lib/tzx-dram-gpu/runtime.py']=runtime.replace(OLD_PANFROST.encode(),manifest['panfrost_sha256'].encode())
        gpu_proof=Path('/var/lib/tzx/gpu-qualified').read_bytes()
        assert OLD_PANFROST.encode() in gpu_proof
        mirrors['/var/lib/tzx/gpu-qualified']=gpu_proof.replace(OLD_PANFROST.encode(),manifest['panfrost_sha256'].encode())
        hs=Path('/usr/local/lib/tzx-emmc-hs/manifest.json')
        v=json.loads(hs.read_text())
        assert v['kernel_image_sha256']=='4c47d5cf91a544b0c9d47901309b0bca8e8ff71320f91a4088da37ab565615fc'
        assert v['boot_header_sha256']=='47e503b504a0b4260a3509fccad1918408058ffe47a8cbb9e9b84f7abed91d1f'
        v['kernel_image_sha256']=manifest['items'][0]['sha256'];v['boot_header_sha256']=manifest['header_sha256']
        hs_runtime=Path('/usr/local/lib/tzx-emmc-hs/runtime.py')
        hs_source=hs_runtime.read_text()
        assert v['files'][str(hs_runtime)]==sha(hs_runtime.read_bytes())
        needle="""        temperatures=[int(p.read_text()) for p in Path('/sys/class/thermal').glob('thermal_zone*/temp')]
        assert len(temperatures)==6 and all(0<t<80000 for t in temperatures)"""
        assert hs_source.count(needle)==1
        hs_source=hs_source.replace(needle,"""        # CPU cooler replacement can temporarily remove the aggregate zone.
        # Require every physical sensor; do not count optional aggregate zones.
        physical={'cpu-big-thermal','cpu-little-thermal','gpu-thermal','npu-thermal','ddr-thermal'}
        observed={}
        for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
            try:
                name=(zone/'type').read_text().strip()
                if name in physical:observed[name]=int((zone/'temp').read_text())
            except FileNotFoundError:pass
        assert set(observed)==physical
        temperatures=list(observed.values())
        assert all(0<t<80000 for t in temperatures)""")
        mirrors[str(hs_runtime)]=hs_source.encode()
        v['files'][str(hs_runtime)]=sha(hs_source.encode())
        mirrors[str(hs)]=(json.dumps(v,indent=2)+'\n').encode()
        backup.mkdir(parents=True)
        atomic(backup/'hs-v4-bundle.bin',old)
        before={}
        for name,data in mirrors.items():
            p=Path(name);saved=p.read_bytes();mode=p.stat().st_mode&0o777
            atomic(backup/'files'/name.lstrip('/'),saved,mode)
            before[name]={'mode':mode,'sha256':sha(saved),'replacement_sha256':sha(data)}
        record(backup/'before.json',dict(boot_id=BOOT,files=before,manifest_pin=pin))
        # Select the untouched recovery slot BEFORE overwriting the former
        # active slot. An interrupted write then leaves a bootable bundle.
        assert os.pwrite(fd,fallback[:512],4096*512)==512;os.fsync(fd)
        assert os.pread(fd,512,4096*512)==fallback[:512]
        record(state_path,dict(state='fallback-selected-while-writing',installed_boot_id=BOOT,manifest=manifest,backup=str(backup)))
        for off in range(0,len(candidate),1024*1024):
            chunk=candidate[off:off+1024*1024]
            assert os.pwrite(fd,chunk,98304*512+off)==len(chunk)
        os.fsync(fd);assert os.pread(fd,len(candidate),98304*512)==candidate
        for name,data in mirrors.items():atomic(Path(name),data)
        assert os.pwrite(fd,candidate[:512],4096*512)==512;os.fsync(fd)
        assert os.pread(fd,512,4096*512)==candidate[:512]
        record(state_path,dict(state='selected-pending-reboot',installed_boot_id=BOOT,manifest=manifest,backup=str(backup)))
        print('CPU_GPU_KERNEL_INSTALLED_VERIFIED_WITH_INTACT_FALLBACK',manifest['sha256'],flush=True)
    elif operation=='restore':
        before=json.loads((backup/'before.json').read_text());assert before['manifest_pin']==pin
        old=(backup/'hs-v4-bundle.bin').read_bytes();assert sha(old)==OLD
        # The recovery slot remains selected until the complete old HS image
        # and every guarded runtime mirror have been restored and read back.
        assert os.pwrite(fd,fallback[:512],4096*512)==512;os.fsync(fd)
        assert os.pwrite(fd,old,98304*512)==len(old);os.fsync(fd)
        assert os.pread(fd,len(old),98304*512)==old
        for name,item in before['files'].items():
            data=(backup/'files'/name.lstrip('/')).read_bytes();assert sha(data)==item['sha256']
            atomic(Path(name),data,item['mode'])
        assert os.pwrite(fd,old[:512],4096*512)==512;os.fsync(fd)
        record(state_path,dict(state='restored-HS-v4',backup=str(backup),restored_boot_id=BOOT))
        print('CPU_GPU_KERNEL_PRIOR_HS_V4_RESTORED',flush=True)
    else:
        assert os.pread(fd,512,4096*512)==candidate[:512]
        assert os.pread(fd,len(candidate),98304*512)==candidate
        assert sha(gzip.decompress(Path('/proc/config.gz').read_bytes()))==manifest['config_sha256']
        assert 'tzx_topology_refresh_capacity' in Path('/proc/kallsyms').read_text()
        state=json.loads(state_path.read_text());assert state['installed_boot_id']!=BOOT
        before=json.loads((backup/'before.json').read_text())
        for name,item in before['files'].items():assert sha(Path(name).read_bytes())==item['replacement_sha256'],name
        run('python3','/usr/local/lib/tzx-dram-gpu/runtime.py','guard')
        assert Path('/sys/class/graphics/fbcon/rotate').read_text().strip()=='1'
        state.update(state='actual-normal-boot-verified',verified_boot_id=BOOT)
        record(state_path,state)
        print('CPU_GPU_KERNEL_ACTUAL_BOOT_AND_RUNTIME_MIRRORS_PASS',BOOT,flush=True)
    assert os.pread(fd,40960,256*512)==toc
    assert os.pread(fd,15008768,65536*512)==fallback
    assert os.pread(fd,len(primary),0)==primary
    assert os.pread(fd,len(secondary),(244318208-33)*512)==secondary
finally:
    os.close(fd)
os.sync()
print('TRAINED_LOADER_GPT_AND_RECOVERY_SLOT_PRESERVED',flush=True)
