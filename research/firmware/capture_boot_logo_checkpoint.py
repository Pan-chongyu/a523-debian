"""Capture exact installed image delta, verified raw bytes and rollback before-images."""
import hashlib,io,json,os,subprocess,tarfile,time
from pathlib import Path

assert os.geteuid()==0
state=Path('/var/lib/tzx');boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
proof=json.loads((state/'boot-logo-qualified.json').read_text())
installed=json.loads((state/'boot-logo-installed.json').read_text())
load=json.loads((state/'cpu-gpu-integration-qualified.json').read_text())
assert proof['boot_id']==load['boot_id']==boot and proof['status']==load['status']=='PASS'
sha=lambda data:hashlib.sha256(data).hexdigest()
content={};modes={}

def add(path):
    path=Path(path);assert path.is_absolute() and path.is_file() and not path.is_symlink(),path
    assert not any(part in str(path).lower() for part in ('private/','.ssh','password','credential','__pycache__'))
    name=str(path).lstrip('/');data=path.read_bytes();assert len(data)<16*1024*1024,path
    assert name not in content or content[name]==data
    content[name]=data;modes[name]=path.stat().st_mode&0o777

for name,item in installed['files'].items():
    if name!='/var/lib/tzx/boot-panel-installed.json':
        assert sha(Path(name).read_bytes())==item['installed_sha256'],name
    add(name)
for folder in ('/root/tzx-recovery/boot-logo-v1','/home/debian/boot-logo'):
    for path in Path(folder).rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:add(path)
for name in ('boot-logo-installed','boot-logo-qualified','boot-logo-stage','boot-panel-installed',
             'screen-boot-health','dram-gpu-boot-health','cpu-gpu-integration-qualified',
             'boot-latency-qualified','emmc-hs-qualified','cpu-full-qualified','gpu-devfreq-qualified'):
    add(state/(name+'.json'))
add(state/'gpu-qualified')
for name in ('tzx-boot-logo-handoff','tzx-performance-mode','tzx-cpu-dvfs','tzx-gpu-performance','tzx-emmc-hs'):
    add('/run/'+name+'.json')
for name in ('install_boot_logo','verify_boot_logo','repair_boot_logo_handoff',
             'repair_boot_logo_emmc','finalize_boot_logo_validation','capture_boot_logo_checkpoint',
             'verify_boot_panel_native_stack','verify_cpu_gpu_integration'):
    add('/home/debian/'+name+'.py')
add('/home/debian/boot-logo-stage.tar.gz')
fd=os.open('/dev/mmcblk0',os.O_RDONLY)
try:
    for name,lba,size,expected in (
        ('toc0.bin',256,49152,installed['toc0_sha256']),
        ('payload.bin',49152,925696,json.loads(Path('/home/debian/boot-logo/loader.toc0.json').read_text())['payload_sha256']),
        ('active-header.bin',4096,512,installed['raw_invariants']['header']),
        ('active-bundle.bin',98304,15008768,installed['raw_invariants']['active'])):
        data=os.pread(fd,size,lba*512);assert len(data)==size and sha(data)==expected,name
        content['raw-current/'+name]=data;modes['raw-current/'+name]=0o600
finally:os.close(fd)
for name,args in (
    ('kernel.txt',['journalctl','-b','-k','--no-pager']),
    ('boot-units.txt',['journalctl','-b','--no-pager','-u','tzx-boot-panel-handoff','-u','tzx-touch',
         '-u','tzx-display','-u','lightdm','-u','tzx-cpu-performance-mode','-u','tzx-emmc-hs'])):
    content['evidence/'+name]=subprocess.check_output(args,timeout=40);modes['evidence/'+name]=0o600
assert boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert not subprocess.check_output(['systemctl','--failed','--no-legend','--plain'],text=True).strip()
manifest=dict(profile='TZX-A523-right-landscape-custom-boot-image-v1-handoff-revision2',
    boot_id=boot,captured_unix=int(time.time()),toc0_sha256=installed['toc0_sha256'],
    qualification=installed['qualification'],raw_invariants=installed['raw_invariants'],
    files={name:sha(data) for name,data in content.items()},modes=modes,
    rollback_commands=['python3 /home/debian/install_boot_logo.py restore '+installed['toc0_sha256'],
                       'systemctl reboot'],
    paired_checkpoint='max-performance-installed-checkpoint.tar.gz',
    paired_checkpoint_sha256='ad7ac9ce6f849784b14dd6596937df934cc390a906ef307442ab7df7b87d5c7f',
    rootfs_backup=False,credentials_included=False)
target=Path('/home/debian/boot-logo-installed-checkpoint.tar.gz');assert not target.exists()
with tarfile.open(target,'w:gz') as archive:
    for name,data in dict(content,**{'MANIFEST.json':(json.dumps(manifest,indent=2)+'\n').encode()}).items():
        member=tarfile.TarInfo(name);member.size=len(data);member.mode=modes.get(name,0o600)
        archive.addfile(member,io.BytesIO(data))
target.chmod(0o644)
print('BOOT_LOGO_INSTALLED_CHECKPOINT_CREATED',json.dumps(dict(path=str(target),files=len(content),
    bytes=target.stat().st_size,sha256=sha(target.read_bytes()))),flush=True)
