"""Capture a scoped optimized-boot delta paired with the frozen CPU/GPU package."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time
assert os.geteuid()==0
state=Path('/var/lib/tzx');boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
proof=json.loads((state/'fast-boot-key-on-qualified.json').read_text())
assert proof['status']=='PASS' and proof['boot_id']==boot and proof['poweroff_key_on_verified']
assert proof['toc0_sha256']=='50537c7ff9d9b20461c0a1181f3b4f04240e63be7aece9f49ba1ce6c18bc0c9b'
sha=lambda b:hashlib.sha256(b).hexdigest()
content={};modes={}
def add(path):
    path=Path(path)
    assert path.is_absolute() and path.is_file() and not path.is_symlink(),path
    assert not any(v in str(path).lower() for v in ('.ssh','private','password','credential','__pycache__'))
    data=path.read_bytes();assert len(data)<4*1024*1024,path
    name=path.as_posix().lstrip('/')
    if name in content:assert content[name]==data
    content[name]=data;modes[name]=path.stat().st_mode&0o777
for name in ('tzx-cpub','tzx-display'):
    add('/etc/systemd/system/'+name+'.service')
for name in ('tzx-cpu-dvfs','tzx-gpu-performance','tzx-emmc-hs'):
    add('/etc/systemd/system/'+name+'.service.d/99-clean-shutdown.conf')
    add('/run/'+name+'.json')
for name in ('tzx-dram-gpu','tzx-rtc-context','tzx-pmic-poweroff'):
    add('/usr/local/lib/'+name+'/runtime.py')
for name in ('tzx-cpu-full','tzx-gpu-devfreq','tzx-emmc-hs'):
    manifest=Path('/usr/local/lib')/name/'manifest.json'
    value=json.loads(manifest.read_text())
    for path,digest in value['files'].items():assert sha(Path(path).read_bytes())==digest,path
    add(manifest)
for pattern in ('boot-*-installed.json','boot-latency-qualified.json','fast-boot-key-on-*.json',
                'performance-clean-shutdown.json','cpu-gpu-*-qualified.json'):
    for path in state.glob(pattern):add(path)
for name in ('cpu-full-qualified','gpu-devfreq-qualified','cpu-gpu-native-installed','pmic-poweroff-installed',
             'emmc-hs-qualified','screen-boot-health','dram-gpu-boot-health','cpu-gpu-integration-qualified'):
    add(state/(name+'.json'))
stages=('boot-latency-v1','boot-crc-v1','boot-early-cpub-v1','boot-wide-v1','boot-profile-v1',
        'boot-fast-v1','boot-icache-v1','boot-hwcrc-v1','performance-clean-shutdown-v1')
for name in stages:
    directory=Path('/root/tzx-recovery')/name;assert directory.is_dir(),name
    for path in directory.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:add(path)
for name in ('boot-latency','boot-crc','boot-cpub','boot-wide','boot-profile','boot-fast','boot-icache','boot-hwcrc'):
    add('/home/debian/install_'+name.replace('-','_')+'.py')
for name in ('verify_boot_latency','read_boot_profile','prepare_fast_boot_key_on','qualify_fast_boot_key_on',
             'fix_performance_shutdown','finalize_boot_user_validation','capture_boot_performance_checkpoint'):
    add('/home/debian/'+name+'.py')
for name in ('boot-latency-loader','boot-early-cpub','boot-wide-emmc','boot-profile','boot-fast','boot-icache','boot-hwcrc'):
    for file in ('loader.toc0','loader.toc0.json'):add('/home/debian/'+name+'/'+file)
raw={}
with open('/dev/mmcblk0','rb',buffering=0) as disk:
    for name,lba,length,pin,capture in (
        ('current-toc0.bin',256,40960,proof['toc0_sha256'],True),
        ('active-header.bin',4096,512,'1e07c2743da3e94c0e6f498b4c7a5203c9f7666e3c66b819f64633eb8742ddbb',True),
        ('gpt-primary.bin',0,34*512,None,True),('gpt-secondary.bin',244318208-33,33*512,None,True),
        ('cpu-gpu-active-slot.bin',98304,15008768,'c5d306559886e947d702457a92149e4c2e6c41713188bee6bbbdcc22409f0da7',False),
        ('extended-recovery-slot.bin',65536,15008768,'091ebfe06aa47ca3a4ac7e347838dd6175c575771032e1703e6b7b1480e460e3',False)):
        disk.seek(lba*512);data=disk.read(length);assert len(data)==length
        if pin:assert sha(data)==pin,name
        raw[name]=dict(lba=lba,bytes=length,sha256=sha(data),included=capture)
        if capture:content['raw-emmc/'+name]=data;modes['raw-emmc/'+name]=0o600
for name,args in (
    ('kernel.log',['journalctl','-b','-k','--no-pager']),
    ('boot-units.log',['journalctl','-b','--no-pager','-u','tzx-cpub','-u','tzx-touch','-u','tzx-display','-u','lightdm']),
    ('normal-shutdown.log',['journalctl','-b','-1','--no-pager','-u','tzx-cpu-dvfs','-u','tzx-gpu-performance','-u','tzx-emmc-hs']),
    ('boot-profile.txt',['python3','/home/debian/read_boot_profile.py'])):
    content['evidence/'+name]=subprocess.check_output(args,timeout=45);modes['evidence/'+name]=0o600
assert not subprocess.check_output(['systemctl','--failed','--plain','--no-legend'],text=True).strip()
assert boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
manifest=dict(profile='optimized-boot-and-clean-performance-shutdown-20261113',boot_id=boot,
    captured_unix=int(time.time()),normal_reboot_verified=True,poweroff_key_on_verified=True,
    rootfs_backup=False,files={name:sha(data) for name,data in content.items()},modes=modes,
    raw_boot_readback=raw,paired_base_checkpoint=dict(file='cpu-gpu-native-installed-checkpoint.tar.gz',
    sha256='ef9ba34f1384b79336e8466093fa1d5acdffa72db33b9f3e7165001b01ff7621'),
    restore_note='Scoped delta, not a disk image. Only boot-hwcrc is current; boot-wide and boot-icache were rolled back. Reverse current stages hwcrc,fast,profile,cpub,crc before the old CPU/GPU kernel installer. See BOOT-LATENCY-INTEGRATION.md.')
target=Path('/home/debian/boot-performance-installed-checkpoint-v2.tar.gz');assert not target.exists()
with tarfile.open(target,'w:gz') as archive:
    for name,data in dict(content,**{'MANIFEST.json':(json.dumps(manifest,indent=2)+'\n').encode()}).items():
        item=tarfile.TarInfo(name);item.size=len(data);item.mode=modes.get(name,0o600)
        archive.addfile(item,io.BytesIO(data))
target.chmod(0o644)
print('BOOT_PERFORMANCE_DELTA_CHECKPOINT_CREATED',json.dumps(dict(path=str(target),files=len(content),
    bytes=target.stat().st_size,sha256=sha(target.read_bytes()))),flush=True)
