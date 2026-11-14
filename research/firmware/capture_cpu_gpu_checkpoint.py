"""Capture the exact reboot-qualified CPU/GPU installation and recovery files."""
import hashlib,io,json,os,subprocess,tarfile,time
from pathlib import Path
assert os.geteuid()==0
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
state=Path('/var/lib/tzx')
proof=json.loads((state/'cpu-gpu-normal-reboot-qualified.json').read_text())
assert proof['status']=='PASS' and proof['boot_id']==boot and proof['normal_reboot_verified']
assert not subprocess.check_output(['systemctl','--failed','--no-legend','--plain'],text=True).strip()
sha=lambda b:hashlib.sha256(b).hexdigest()
content={};modes={}
def add(path):
    path=Path(path)
    assert path.is_absolute() and path.is_file() and not path.is_symlink(),str(path)
    assert not any(word in str(path).lower() for word in ('.ssh','private','credential','password'))
    data=path.read_bytes();assert len(data)<16*1024*1024
    name=path.as_posix().lstrip('/')
    if name in content:assert content[name]==data
    content[name]=data;modes[name]=path.stat().st_mode&0o777
installed=json.loads((state/'cpu-gpu-native-installed.json').read_text())
for name in installed['created_files']:add(name)
kernel_backup=Path('/root/tzx-recovery/cpu-gpu-kernel')
before=json.loads((kernel_backup/'before.json').read_text())
for name,item in before['files'].items():
    assert sha(Path(name).read_bytes())==item['replacement_sha256'],name
    add(name)
for directory in ('/usr/local/lib/tzx-cpufreq','/usr/local/lib/tzx-cpu-cooling',
                  '/usr/local/lib/tzx-cpu-dvfs','/usr/local/lib/tzx-gpu-performance',
                  '/usr/local/lib/tzx-emmc-hs','/root/tzx-recovery/cpu-gpu-kernel',
                  '/root/tzx-recovery/cpu-gpu-native-runtime',
                  '/root/tzx-recovery/native-cooling-inventory','/root/tzx-recovery/gpu-native-guard-v2'):
    for path in sorted(Path(directory).rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:add(path)
for name in ('tzx-cpufreq','tzx-cpu-cooling','tzx-cpu-dvfs','tzx-gpu-performance',
             'tzx-gpu','tzx-dram-gpu-fallback','tzx-dram-gpu-health'):
    add('/etc/systemd/system/'+name+'.service')
for unit in ('tzx-gpu','tzx-gpu-performance','tzx-dram-gpu-fallback'):
    for path in Path('/etc/systemd/system/'+unit+'.service.d').glob('*.conf'):add(path)
for name in ('cpu-gpu-native-installed','cpu-gpu-kernel-installed','cpu-gpu-normal-reboot-request',
             'cpu-gpu-normal-reboot-qualified','cpu-gpu-integration-qualified','cpu-full-qualified',
             'gpu-devfreq-qualified','gpu-native-guard-v2-controls','native-gpu-cooling-controls',
             'emmc-hs-qualified','emmc-hs-installed','cpu-cooling-installed',
             'screen-boot-health','screen-installed','screen-qualified',
             'dram-gpu-boot-health','dram-gpu-runtime-installed'):
    add(state/(name+'.json'))
for name in ('cpu-dvfs','gpu-performance','emmc-hs'):add('/run/tzx-'+name+'.json')
for path in ('/home/debian/cpu-gpu-kernel/install_cpu_gpu_kernel.py',
             '/home/debian/cpu-gpu-kernel/linux-bundle.json','/home/debian/cpu-gpu-kernel/kernel.config',
             '/home/debian/install_cpu_gpu_runtime.py','/home/debian/cpu-gpu-runtime.tar.gz',
             '/home/debian/upgrade_gpu_native_guard.py','/home/debian/qualify_cpu_gpu_reboot.py',
             '/home/debian/prepare_cpu_gpu_reboot.py','/home/debian/verify_cpu_gpu_integration.py',
             '/home/debian/verify_native_gpu_cooling.py','/home/debian/verify_gpu_compute.py',
             '/home/debian/verify_safe_memory.py','/home/debian/tzx_direct_io.py',
             '/home/debian/cpu-full/trial-result.json','/home/debian/gpu-devfreq/trial-result.json',
             '/home/debian/cpu-gpu-validation/result.json',
             '/home/debian/capture_cpu_gpu_checkpoint.py'):
    add(path)
raw={}
with Path('/dev/mmcblk0').open('rb',buffering=0) as disk:
    for name,lba,length,pin in (
        ('trained-toc0.bin',256,40960,'311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75'),
        ('active-header.bin',4096,512,'1e07c2743da3e94c0e6f498b4c7a5203c9f7666e3c66b819f64633eb8742ddbb'),
        ('extended-recovery-slot.bin',65536,15008768,'091ebfe06aa47ca3a4ac7e347838dd6175c575771032e1703e6b7b1480e460e3'),
        ('cpu-gpu-active-slot.bin',98304,15008768,'c5d306559886e947d702457a92149e4c2e6c41713188bee6bbbdcc22409f0da7'),
        ('gpt-primary.bin',0,34*512,None),('gpt-secondary.bin',244318208-33,33*512,None)):
        disk.seek(lba*512);data=disk.read(length);assert len(data)==length
        if pin:assert sha(data)==pin,name
        content['raw-emmc/'+name]=data;modes['raw-emmc/'+name]=0o600
        raw[name]=dict(lba=lba,bytes=length,sha256=sha(data))
for name,args in (
    ('kernel.log',['journalctl','-b','-k','--no-pager']),
    ('normal-reboot-stop.log',['journalctl','-b','-1','--no-pager','-u','tzx-cpu-dvfs','-u','tzx-gpu-performance','-u','tzx-emmc-hs']),
    ('services.txt',['systemctl','status','--no-pager','tzx-cpu-dvfs','tzx-gpu-performance','tzx-emmc-hs'])):
    content['evidence/'+name]=subprocess.check_output(args,timeout=30);modes['evidence/'+name]=0o600
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
manifest=dict(profile='cpu-gpu-native-20261113',boot_id=boot,captured_unix=int(time.time()),
    normal_reboot_verified=True,poweroff_key_on_verified=False,rootfs_backup=False,
    files={name:sha(data) for name,data in content.items()},modes=modes,symlinks={},
    raw_boot_readback=raw,limits=proof['limits'],
    paired_previous_checkpoint=dict(file='advanced-performance-installed-checkpoint.tar.gz',
        sha256='16cd5bc7b43ab16dbeab21a2718e366e3365e2d5e48bfce19a339e342cf3b7c3'),
    restore_note='Scoped files and boot areas; do not flash the archive. Restore runtime first, then use the pinned kernel installer restore operation. LBA65536 is the intact recovery bundle. See CPU-GPU-FULL-INTEGRATION.md.')
target=Path('/home/debian/cpu-gpu-native-installed-checkpoint.tar.gz')
assert not target.exists()
with tarfile.open(target,'w:gz') as archive:
    for name,data in dict(content,**{'MANIFEST.json':(json.dumps(manifest,indent=2)+'\n').encode()}).items():
        entry=tarfile.TarInfo(name);entry.size=len(data);entry.mode=modes.get(name,0o600)
        archive.addfile(entry,io.BytesIO(data))
target.chmod(0o644)
print('CPU_GPU_INSTALLED_CHECKPOINT_CREATED',json.dumps(dict(path=str(target),bytes=target.stat().st_size,
    sha256=sha(target.read_bytes()),files=len(content))),flush=True)
