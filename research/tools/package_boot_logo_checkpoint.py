"""Freeze the reviewed splash sources, exact build output and device evidence."""
import hashlib,io,json,tarfile
from pathlib import Path,PurePosixPath
root=Path(__file__).resolve().parents[1]
installed=json.loads((root/'build/boot-logo-installed-checkpoint.json').read_text())
assert installed['every_member_verified'] and installed['qualification']['normal_reboot_verified']
sha=lambda data:hashlib.sha256(data).hexdigest();content={}

def add(path):
    path=Path(path);assert path.is_file() and not path.is_symlink(),path
    name=path.relative_to(root).as_posix()
    assert not any(value in name.lower() for value in ('private/','.ssh','password','credential','__pycache__'))
    content[name]=path.read_bytes()

for name in ('boot_logo.c','boot_logo_loader.c','install_boot_logo.py','verify_boot_logo.py',
    'repair_boot_logo_handoff.py','repair_boot_logo_emmc.py','finalize_boot_logo_validation.py',
    'capture_boot_logo_checkpoint.py','boot_panel_handoff.py','tzx_de_scanout.c'):
    add(root/'firmware'/name)
for name in ('prepare_boot_logo.py','build_boot_logo.sh','prepare_boot_logo_bundle.py',
    'prepare_boot_logo_runtime.py','verify_boot_logo_emulation.py','package_boot_logo.py',
    'pull_boot_logo_checkpoint.py','package_boot_logo_checkpoint.py','make_toc0.py','fel_device.py'):
    add(root/'tools'/name)
for path in (root/'build/boot-logo').iterdir():
    if path.is_file():add(path)
for path in (root/'evidence').glob('boot-logo*'):
    if path.is_file():add(path)
for name in ('BOOT-SPLASH.md','PROGRESS.md','build/boot-logo-installed-checkpoint.json',
    'build/boot-logo-stage.tar.gz','build/boot-logo-stage-first-trial.tar.gz',
    'build/max-performance-source-checkpoint.tar.gz','build/max-performance-installed-checkpoint.json',
    'build/boot-cpu-performance/loader.bin','build/boot-cpu-performance/loader.toc0',
    'build/boot-panel-early-v2/panel-hook.disassembly.txt',
    'build/cpu-gpu-kernel/linux-bundle.bin','build/cpu-gpu-kernel/linux-bundle.json',
    'evidence/initial-fel/toc0-descriptor.bin'):
    add(root/name)
manifest=dict(profile='TZX-A523-custom-boot-image-v1-handoff-revision2-source',boot_id=installed['boot_id'],
    installed_archive_sha256=installed['archive_sha256'],
    files={name:sha(data) for name,data in content.items()},credentials_included=False,
    signing_private_key_included=False)
target=root/'build/boot-logo-source-checkpoint.tar.gz';assert not target.exists()
with tarfile.open(target,'w:gz') as archive:
    for name,data in dict(content,**{'MANIFEST.json':(json.dumps(manifest,indent=2)+'\n').encode()}).items():
        member=tarfile.TarInfo(name);member.size=len(data);member.mode=0o600
        archive.addfile(member,io.BytesIO(data))
with tarfile.open(target) as archive:
    members=archive.getmembers();assert len(members)==len({member.name for member in members})==len(content)+1
    for member in members:
        name=PurePosixPath(member.name);assert member.isfile() and not name.is_absolute() and '..' not in name.parts
    for name,digest in manifest['files'].items():assert sha(archive.extractfile(name).read())==digest,name
record=dict(manifest,archive_sha256=sha(target.read_bytes()),archive_bytes=target.stat().st_size,every_member_verified=True)
(root/'build/boot-logo-source-checkpoint.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('BOOT_LOGO_SOURCE_EVERY_MEMBER_VERIFIED',json.dumps(dict(files=len(content),
    bytes=record['archive_bytes'],sha256=record['archive_sha256'])),flush=True)
