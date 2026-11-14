"""Capture the small startup delta and exact rollback files without user data."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time

assert os.geteuid()==0
state=Path('/var/lib/tzx')
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
proof=json.loads((state/'screen-fast-final-qualified.json').read_text())
assert proof['status']=='PASS' and proof['boot_id']==boot and proof['poweroff_key_on_verified']
installed=json.loads((state/'screen-fast-installed.json').read_text())
user=json.loads((state/'screen-fast-user-confirmed.json').read_text())
assert user['boot_id']==boot and user['right_landscape_and_touch_confirmed']
sha=lambda b:hashlib.sha256(b).hexdigest()
content={}
modes={}

def add(path):
    path=Path(path)
    assert path.is_absolute() and path.is_file() and not path.is_symlink(),path
    assert not any(s in str(path).lower() for s in ('.ssh','private','password','credential','__pycache__'))
    data=path.read_bytes()
    assert len(data)<2*1024*1024,path
    name=path.as_posix().lstrip('/')
    assert name not in content or content[name]==data
    content[name]=data
    modes[name]=path.stat().st_mode&0o777

for name,item in installed['files'].items():
    assert sha(Path(name).read_bytes())==item['installed_sha256'],name
    add(name)
for path in state.glob('screen-fast-*.json'):
    add(path)
for name in ('screen-boot-health','dram-gpu-boot-health','boot-latency-qualified','cpu-gpu-integration-qualified',
             'cpu-full-qualified','gpu-devfreq-qualified','emmc-hs-qualified','performance-clean-shutdown'):
    add(state/(name+'.json'))
for name in ('/run/tzx-touch-rail-ready.json','/run/tzx-touch-input-ready.json',
             '/run/tzx-cpu-dvfs.json','/run/tzx-gpu-performance.json','/run/tzx-emmc-hs.json',
             '/var/lib/tzx/gpu-qualified','/var/lib/tzx/screen-qualified.json'):
    add(name)
backup=Path(installed['backup'])
assert str(backup)=='/root/tzx-recovery/screen-fast-rail-v1'
for path in backup.rglob('*'):
    if path.is_file() and '__pycache__' not in path.parts:
        add(path)
for name in ('install_screen_fast_boot','screen_fast_touch_ready','advance_screen_rail_notification',
             'fix_screen_fast_overlay_order','prepare_screen_fast_reboot','qualify_screen_fast_boot',
             'prepare_screen_fast_key_on','verify_screen_fast_final','finalize_screen_fast_validation',
             'capture_screen_fast_checkpoint'):
    add('/home/debian/'+name+'.py')
for name,args in (
    ('kernel.log',['journalctl','-b','-k','--no-pager']),
    ('screen-units.log',['journalctl','-b','--no-pager','-u','tzx-touch','-u','tzx-touch-input-ready',
                        '-u','tzx-display','-u','tzx-thermal','-u','tzx-video','-u','lightdm']),
    ('boot-critical-chain.txt',['systemd-analyze','critical-chain','tzx-display.service','lightdm.service']),
    ('boot-profile.txt',['python3','/home/debian/read_boot_profile.py'])):
    content['evidence/'+name]=subprocess.check_output(args,timeout=40)
    modes['evidence/'+name]=0o600
assert boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert not subprocess.check_output(['systemctl','--failed','--plain','--no-legend'],text=True).strip()
manifest=dict(profile='screen-early-first-frame-startup-delta-20261113',boot_id=boot,
    captured_unix=int(time.time()),normal_reboot_verified=True,poweroff_key_on_verified=True,
    raw_boot_changed=False,raw_boot_pins=installed['raw_boot_unchanged'],
    files={name:sha(data) for name,data in content.items()},modes=modes,
    paired_boot_checkpoint=dict(file='boot-performance-installed-checkpoint-v2.tar.gz',
        sha256='fce36e72ecd274d45dc70d3e4136a6fd096bbd333bd351b9ffccc3f42a47ec7c'),
    paired_CPU_GPU_base=dict(file='cpu-gpu-native-installed-checkpoint.tar.gz',
        sha256='ef9ba34f1384b79336e8466093fa1d5acdffa72db33b9f3e7165001b01ff7621'),
    restore_note='Scoped delta; not an image. Restore the eight startup files with install_screen_fast_boot.py restore before undoing older startup ordering. No raw boot write in this delta. Historical failed-trial proofs retained.',
    rootfs_backup=False,credentials_included=False)
target=Path('/home/debian/screen-fast-installed-checkpoint.tar.gz')
assert not target.exists()
with tarfile.open(target,'w:gz') as archive:
    for name,data in dict(content,**{'MANIFEST.json':(json.dumps(manifest,indent=2)+'\n').encode()}).items():
        item=tarfile.TarInfo(name)
        item.size=len(data)
        item.mode=modes.get(name,0o600)
        archive.addfile(item,io.BytesIO(data))
target.chmod(0o644)
assert target.stat().st_size<1024*1024
print('SCREEN_FAST_INSTALLED_CHECKPOINT_CREATED',json.dumps(dict(path=str(target),files=len(content),
    bytes=target.stat().st_size,sha256=sha(target.read_bytes()))),flush=True)
