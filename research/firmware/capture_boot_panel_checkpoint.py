"""Freeze the installed early-panel delta, proofs and both exact rollback steps."""
import hashlib,io,json,os,subprocess,tarfile,time
from pathlib import Path

assert os.geteuid()==0
state=Path('/var/lib/tzx');boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
proof=json.loads((state/'boot-panel-final-qualified.json').read_text())
assert proof['status']=='PASS' and proof['boot_id']==boot
installed=json.loads((state/'boot-panel-installed.json').read_text())
sha=lambda b:hashlib.sha256(b).hexdigest()
content={};modes={}
def add(path):
    path=Path(path)
    assert path.is_absolute() and path.is_file() and not path.is_symlink(),path
    assert not any(s in str(path).lower() for s in ('private','.ssh','password','credential','__pycache__'))
    data=path.read_bytes();assert len(data)<2*1024*1024,path
    name=str(path).lstrip('/')
    assert name not in content or content[name]==data
    content[name]=data;modes[name]=path.stat().st_mode&0o777
for name,item in installed['files'].items():
    assert sha(Path(name).read_bytes())==item['installed_sha256'],name
    add(name)
for folder in ('/root/tzx-recovery/boot-panel-early-v1','/root/tzx-recovery/boot-panel-early-v2',
               '/home/debian/boot-panel-early','/home/debian/boot-panel-early-v2'):
    for p in Path(folder).rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:add(p)
for p in state.glob('boot-panel-*.json'):add(p)
for name in ('boot-latency-qualified','screen-boot-health','dram-gpu-boot-health','cpu-gpu-integration-qualified',
    'cpu-full-qualified','gpu-devfreq-qualified','emmc-hs-qualified','performance-clean-shutdown'):
    add(state/(name+'.json'))
for name in ('gpu-qualified','screen-qualified.json'):add(state/name)
for name in ('install_boot_panel','install_boot_panel_v2','boot_panel_handoff','boot_panel_handoff_v2',
    'boot_panel_handoff_fixed','repair_boot_panel_handoff','prepare_boot_panel_trial','qualify_boot_panel',
    'verify_boot_panel_native_stack','verify_boot_panel_final','finalize_boot_panel_validation',
    'capture_boot_panel_checkpoint'):
    add('/home/debian/'+name+'.py')
for name,args in (
    ('kernel.txt',['journalctl','-b','-k','--no-pager']),
    ('boot-units.txt',['journalctl','-b','--no-pager','-u','tzx-boot-panel-handoff','-u','tzx-touch',
        '-u','tzx-display','-u','lightdm','-u','tzx-screen-health']),
    ('boot-profile.txt',['python3','/home/debian/read_boot_profile.py'])):
    content['evidence/'+name]=subprocess.check_output(args,timeout=40);modes['evidence/'+name]=0o600
assert boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert not subprocess.check_output(['systemctl','--failed','--plain','--no-legend'],text=True).strip()
manifest=dict(profile='TZX-A523-SRAM-panel-early-v2-CCF-handoff-fixed',boot_id=boot,
    captured_unix=int(time.time()),toc0_sha256=installed['toc0_sha256'],toc0_bytes=49152,
    raw_invariants=installed['raw_invariants'],files={n:sha(b) for n,b in content.items()},modes=modes,
    first_backlight_SRAM_counter_s=proof['PMIC_key_on_qualified']['SRAM_receipt']['lit_counter_s'],
    paired_checkpoints=['screen-fast-installed-checkpoint.tar.gz',
        'boot-performance-installed-checkpoint-v2.tar.gz','cpu-gpu-native-installed-checkpoint.tar.gz'],
    rollback='Run install_boot_panel_v2.py restore with current pin, then install_boot_panel.py restore with v1 pin. Both exact before-images and guards included.',
    rootfs_backup=False,credentials_included=False)
target=Path('/home/debian/boot-panel-installed-checkpoint.tar.gz');assert not target.exists()
with tarfile.open(target,'w:gz') as archive:
    for name,data in dict(content,**{'MANIFEST.json':(json.dumps(manifest,indent=2)+'\n').encode()}).items():
        item=tarfile.TarInfo(name);item.size=len(data);item.mode=modes.get(name,0o600)
        archive.addfile(item,io.BytesIO(data))
target.chmod(0o644);assert target.stat().st_size<1024*1024
print('EARLY_PANEL_INSTALLED_CHECKPOINT_CREATED',json.dumps(dict(path=str(target),files=len(content),
    bytes=target.stat().st_size,sha256=sha(target.read_bytes()))),flush=True)
