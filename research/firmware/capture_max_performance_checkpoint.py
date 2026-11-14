"""Capture exact installed performance files, raw boot before/after, and evidence."""
import hashlib,io,json,os,subprocess,tarfile
from pathlib import Path
assert os.geteuid()==0
state=Path('/var/lib/tzx');boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
proof=json.loads((state/'performance-mode-final-qualified.json').read_text())
assert proof['boot_id']==boot and proof['status']=='PASS'
sha=lambda data:hashlib.sha256(data).hexdigest()
content={};modes={}
def add(path):
    path=Path(path);assert path.is_absolute() and path.is_file() and not path.is_symlink(),path
    name=path.as_posix().lstrip('/')
    assert not any(value in name.lower() for value in ('private/','.ssh','password','credential','__pycache__'))
    data=path.read_bytes();assert len(data)<4*1024*1024,(path,len(data))
    content[name]=data;modes[name]=path.stat().st_mode&0o777
for record_name in ('performance-mode-installed','boot-cpu-performance-installed'):
    record=json.loads((state/(record_name+'.json')).read_text())
    for name,item in record['files'].items():
        if name!='/var/lib/tzx/boot-panel-installed.json':assert sha(Path(name).read_bytes())==item['installed_sha256'],name
        add(name)
for folder in ('performance-mode-v1','boot-cpu-performance-v1','app-launch-v1'):
    for path in Path('/root/tzx-recovery',folder).rglob('*'):
        if path.is_file() and '__pycache__' not in str(path):add(path)
for path in Path('/home/debian/boot-cpu-performance').iterdir():
    if path.is_file():add(path)
for name in ('performance-mode-installed','performance-mode-final-qualified','performance-mode-idle-qualified',
    'performance-mode-caps-qualified','boot-cpu-performance-installed','boot-cpu-performance-qualified',
    'app-launch-installed','app-launch-retry','boot-latency-qualified','cpu-gpu-integration-qualified',
    'screen-boot-health','dram-gpu-boot-health'):
    add(state/(name+'.json'))
for name in ('tzx-performance-mode','tzx-cpu-dvfs','tzx-gpu-performance','tzx-emmc-hs','tzx-early-performance-check'):
    add('/run/'+name+'.json')
for name in ('install_performance_mode','upgrade_early_performance','install_boot_cpu_performance',
    'tzx_performance_mode','tzx_early_performance_check','tzx_cpu_early_performance_runtime',
    'tzx_gpu_max_performance_runtime','tzx_gpu_max_performance_startup','verify_performance_mode',
    'verify_boot_cpu_performance','verify_max_performance_caps','profile_app_launch',
    'install_app_launch','requalify_after_browser_probe','capture_max_performance_checkpoint'):
    add('/home/debian/'+name+'.py')
for label in ('performance-mode-post-reboot',):add('/home/debian/app-launch-profile/'+label+'.json')
for name,command in (
    ('current-kernel.log',['journalctl','-b','-k','--no-pager']),
    ('performance-units.log',['journalctl','-b','--no-pager','-u','tzx-cpu-dvfs','-u','tzx-gpu','-u','tzx-gpu-performance','-u','tzx-cpu-performance-mode','-u','tzx-early-performance-check'])):
    data=subprocess.check_output(command,timeout=30);assert len(data)<4*1024*1024
    content['evidence/'+name]=data;modes['evidence/'+name]=0o600
manifest=dict(profile='TZX-A523-qualified-early-CPU-GPU-max-performance-no-preload',boot_id=boot,
    files={name:sha(data) for name,data in content.items()},modes=modes,
    rollback_commands=['python3 /home/debian/install_boot_cpu_performance.py restore '+proof['toc0_sha256'],
        'python3 /home/debian/upgrade_early_performance.py restore','systemctl reboot'],
    paired_checkpoint_sha256='581751763ede6ff0aa599f05701b12935194ee1bf4541f4c01bd5795b9794582',
    rootfs_backup=False,credentials_included=False)
target=Path('/home/debian/max-performance-installed-checkpoint.tar.gz');assert not target.exists()
with tarfile.open(target,'w:gz') as archive:
    for name,data in dict(content,**{'MANIFEST.json':(json.dumps(manifest,indent=2)+'\n').encode()}).items():
        member=tarfile.TarInfo(name);member.size=len(data);member.mode=modes.get(name,0o600);archive.addfile(member,io.BytesIO(data))
target.chmod(0o644)
print('MAX_PERFORMANCE_INSTALLED_CHECKPOINT_CREATED',json.dumps(dict(path=str(target),bytes=target.stat().st_size,
    files=len(content),sha256=sha(target.read_bytes()))),flush=True)
