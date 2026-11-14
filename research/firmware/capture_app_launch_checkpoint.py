"""Freeze the installed overlay, original launchers, trials and recovery scripts."""
import hashlib,io,json,os,subprocess,tarfile
from pathlib import Path
assert os.geteuid()==0
state=Path('/var/lib/tzx');boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
proof=json.loads((state/'app-launch-final-qualified.json').read_text())
assert proof['boot_id']==boot and proof['status']=='PASS'
installed=json.loads((state/'app-launch-installed.json').read_text())
sha=lambda b:hashlib.sha256(b).hexdigest()
content={};modes={}
def add(path):
    path=Path(path);assert path.is_absolute() and path.is_file() and not path.is_symlink(),path
    name=path.as_posix().lstrip('/')
    assert not any(x in name.lower() for x in ('private/','.ssh','password','credential','__pycache__'))
    data=path.read_bytes();assert len(data)<3*1024*1024,path
    content[name]=data;modes[name]=path.stat().st_mode&0o777
for name,item in installed['files'].items():
    assert sha(Path(name).read_bytes())==item['installed_sha256'];add(name)
for path in Path('/root/tzx-recovery/app-launch-v1').rglob('*'):
    if path.is_file():add(path)
for name in ('app-launch-installed','app-launch-final-qualified','app-launch-controls-qualified',
    'app-launch-reboot-request','app-launch-retry','app-cache-comparison-qualified','boot-latency-qualified',
    'cpu-gpu-integration-qualified','screen-boot-health','dram-gpu-boot-health'):
    add(state/(name+'.json'))
for name in ('tzx-app-boost','tzx-app-cache','tzx-cpu-dvfs','tzx-gpu-performance','tzx-emmc-hs'):
    add('/run/'+name+'.json')
for name in ('profile_app_launch','profile_browser_graphics','trial_app_launch_policy',
    'requalify_after_browser_probe','install_app_launch','upgrade_app_launch_readiness',
    'verify_app_launch_controls','prepare_app_launch_reboot','verify_app_cache_comparison',
    'verify_app_launch_final','capture_app_launch_checkpoint'):
    add('/home/debian/'+name+'.py')
for path in Path('/home/debian/app-launch-profile').glob('*.json'):add(path)
for mode in ('default','noafbc'):
    add('/home/debian/browser-graphics-profile/'+mode+'.json')
for name,cmd in (
    ('kernel.txt',['journalctl','-b','-k','--no-pager']),
    ('app-units.txt',['journalctl','-b','--no-pager','-u','tzx-app-boost','-u','tzx-app-cache'])):
    content['evidence/'+name]=subprocess.check_output(cmd,timeout=30);modes['evidence/'+name]=0o600
manifest=dict(profile='TZX-A523-bounded-app-boost-and-preload-v2',boot_id=boot,
    files={n:sha(b) for n,b in content.items()},modes=modes,
    rollback='python3 /home/debian/install_app_launch.py restore',
    paired_checkpoint_sha256='581751763ede6ff0aa599f05701b12935194ee1bf4541f4c01bd5795b9794582',
    rootfs_backup=False,credentials_included=False)
target=Path('/home/debian/app-launch-installed-checkpoint.tar.gz');assert not target.exists()
with tarfile.open(target,'w:gz') as archive:
    for name,data in dict(content,**{'MANIFEST.json':(json.dumps(manifest,indent=2)+'\n').encode()}).items():
        info=tarfile.TarInfo(name);info.size=len(data);info.mode=modes.get(name,0o600)
        archive.addfile(info,io.BytesIO(data))
target.chmod(0o644)
print('APP_LAUNCH_INSTALLED_CHECKPOINT_CREATED',json.dumps(dict(path=str(target),bytes=target.stat().st_size,
    files=len(content),sha256=sha(target.read_bytes()))),flush=True)
