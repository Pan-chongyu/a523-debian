"""Freeze the verified Linux-stage startup delta before pre-Linux work."""
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import tarfile

root=Path(__file__).resolve().parents[1]
installed=json.loads((root/'build/screen-fast-installed-checkpoint.json').read_text())
assert installed['every_member_verified'] and installed['poweroff_key_on_verified']
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha((root/'build/screen-fast-installed-checkpoint.tar.gz').read_bytes())==installed['archive_sha256']
content={}

def add(path):
    path=Path(path)
    assert path.is_file() and not path.is_symlink()
    name=path.relative_to(root).as_posix()
    assert not any(s in name.lower() for s in ('private/','.ssh','password','credential','__pycache__'))
    assert path.stat().st_size<2*1024*1024
    content[name]=path.read_bytes()

for name in ('inspect_screen_fast_boot','probe_screen_notify_lifecycle','screen_fast_touch_ready',
             'install_screen_fast_boot','prepare_screen_fast_reboot','qualify_screen_fast_boot',
             'fix_screen_fast_overlay_order','advance_screen_rail_notification','prepare_screen_fast_key_on',
             'verify_screen_fast_final','inspect_screen_desktop_start','finalize_screen_fast_validation',
             'capture_screen_fast_checkpoint'):
    add(root/'firmware'/(name+'.py'))
for name in ('tools/tablet_ssh.py','tools/watch_boot.py','tools/pull_screen_fast_checkpoint.py',
             'tools/package_screen_fast_source.py','SCREEN-FAST-BOOT-INTEGRATION.md',
             'BOOT-LATENCY-INTEGRATION.md','DISPLAY-INTEGRATION.md','PROGRESS.md',
             'build/screen-fast-installed-checkpoint.json'):
    add(root/name)
for path in (root/'evidence').glob('screen-fast-*'):
    if path.is_file():
        add(path)
for path in (root/'build/screen-fast').glob('*'):
    if path.is_file():
        add(path)
manifest=dict(profile='verified-Linux-stage-screen-first-frame-source-20261113',
    boot_id=installed['boot_id'],installed_sha256=installed['archive_sha256'],
    files={name:sha(data) for name,data in content.items()},
    not_instant_key_on=True,pre_Linux_display_implemented=False,
    signing_keys_or_rootfs_included=False,
    paired_boot_source_sha256='d1a22478ce1ac3d3fb31ad165b4269807f2b41ca5b03c3b05ffc4ee898c6c0d7')
target=root/'build/screen-fast-source-checkpoint.tar.gz'
assert not target.exists()
with tarfile.open(target,'w:gz') as archive:
    for name,data in dict(content,**{'MANIFEST.json':(json.dumps(manifest,indent=2)+'\n').encode()}).items():
        item=tarfile.TarInfo(name)
        item.size=len(data)
        item.mode=0o600
        archive.addfile(item,io.BytesIO(data))
with tarfile.open(target) as archive:
    members=archive.getmembers()
    assert len(members)==len({m.name for m in members})==len(content)+1
    for item in members:
        path=PurePosixPath(item.name)
        assert item.isfile() and not path.is_absolute() and '..' not in path.parts
    for name,digest in manifest['files'].items():
        assert sha(archive.extractfile(name).read())==digest,name
record=dict(manifest,archive_sha256=sha(target.read_bytes()),archive_bytes=target.stat().st_size,
    every_member_verified=True)
target.with_suffix('').with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('SCREEN_FAST_SOURCE_ALL_MEMBERS_VERIFIED',json.dumps(dict(files=len(content),
    bytes=record['archive_bytes'],sha256=record['archive_sha256'])),flush=True)
