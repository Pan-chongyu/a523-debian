"""Archive the exact early display sources, binaries, test evidence and recovery map."""
import hashlib,io,json,tarfile
from pathlib import Path,PurePosixPath

root=Path(__file__).resolve().parents[1]
installed=json.loads((root/'build/boot-panel-installed-checkpoint.json').read_text(encoding='utf-8'))
assert installed['every_member_verified']
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha((root/'build/boot-panel-installed-checkpoint.tar.gz').read_bytes())==installed['archive_sha256']
proof=json.loads((root/'evidence/boot-panel-final-qualified.json').read_text(encoding='utf-8'))
user=json.loads((root/'evidence/boot-panel-user-confirmed.json').read_text(encoding='utf-8'))
assert proof['status']=='PASS' and proof['boot_id']==installed['boot_id']
assert user['physical_key_on']['right_landscape_and_touch_confirmed']
content={}
def add(path):
    path=Path(path);assert path.is_file() and not path.is_symlink()
    name=path.relative_to(root).as_posix()
    assert not any(s in name.lower() for s in ('private/','.ssh','password','credential','__pycache__'))
    assert path.stat().st_size<2*1024*1024
    content[name]=path.read_bytes()
for name in ('boot_panel_early.c','boot_panel_handoff.py','install_boot_panel.py','install_boot_panel_v2.py',
    'repair_boot_panel_handoff.py','prepare_boot_panel_trial.py','qualify_boot_panel.py',
    'verify_boot_panel_native_stack.py','verify_boot_panel_final.py','finalize_boot_panel_validation.py',
    'capture_boot_panel_checkpoint.py'):
    add(root/'firmware'/name)
for name in ('build_boot_panel.sh','compose_boot_panel.py','verify_boot_panel_emulation.py',
    'prepare_boot_panel_files.py','prepare_boot_panel_verifier.py','pull_boot_panel_checkpoint.py',
    'package_boot_panel_source.py','make_toc0.py','tablet_ssh.py','watch_boot.py','flash_loader_fel.py'):
    add(root/'tools'/name)
for folder in ('build/boot-panel-early','build/boot-panel-early-v2'):
    for path in (root/folder).rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:add(path)
for path in (root/'evidence').glob('boot-panel-*'):
    if path.is_file():add(path)
for name in ('EARLY-PANEL-BOOT.md','PROGRESS.md','DISPLAY-INTEGRATION.md','BOOT-LATENCY-INTEGRATION.md',
    'SCREEN-FAST-BOOT-INTEGRATION.md','build/boot-panel-installed-checkpoint.json'):
    add(root/name)
manifest=dict(profile='TZX-A523-pre-DRAM-panel-and-CCF-handoff-source-20261113',
    boot_id=installed['boot_id'],toc0_sha256=installed['toc0_sha256'],
    installed_archive_sha256=installed['archive_sha256'],
    files={n:sha(b) for n,b in content.items()},signing_private_keys_included=False,
    first_light_user_key_seconds_approx=2,first_backlight_SRAM_counter_s=1.766584,
    hardware_key_on_and_native_desktop_touch_verified=True,
    PMIC_previous_off_source='physical-key REG21=01; software-off not confirmed in this trial',
    paired_boot_source_sha256='d1a22478ce1ac3d3fb31ad165b4269807f2b41ca5b03c3b05ffc4ee898c6c0d7',
    paired_screen_fast_source_sha256='3b36f833863172177d90894c97e4bb97c5a3e056ed330893cce947706036fdb8')
target=root/'build/boot-panel-source-checkpoint.tar.gz';assert not target.exists()
with tarfile.open(target,'w:gz') as archive:
    for name,data in dict(content,**{'MANIFEST.json':(json.dumps(manifest,indent=2)+'\n').encode()}).items():
        item=tarfile.TarInfo(name);item.size=len(data);item.mode=0o600
        archive.addfile(item,io.BytesIO(data))
with tarfile.open(target) as archive:
    members=archive.getmembers();assert len(members)==len({m.name for m in members})==len(content)+1
    for item in members:
        p=PurePosixPath(item.name);assert item.isfile() and not p.is_absolute() and '..' not in p.parts
    for name,digest in manifest['files'].items():assert sha(archive.extractfile(name).read())==digest,name
record=dict(manifest,archive_sha256=sha(target.read_bytes()),archive_bytes=target.stat().st_size,
    every_member_verified=True)
(root/'build/boot-panel-source-checkpoint.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('EARLY_PANEL_SOURCE_EVERY_MEMBER_VERIFIED',json.dumps(dict(files=len(content),bytes=record['archive_bytes'],
    sha256=record['archive_sha256'])),flush=True)
