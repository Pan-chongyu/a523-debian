"""Package the app overlay sources and the exact performance evidence."""
import hashlib,io,json,tarfile
from pathlib import Path,PurePosixPath
root=Path(__file__).resolve().parents[1]
installed=json.loads((root/'build/app-launch-installed-checkpoint.json').read_text(encoding='utf-8'))
assert installed['every_member_verified']
sha=lambda b:hashlib.sha256(b).hexdigest()
content={}
def add(path):
    path=Path(path);assert path.is_file() and not path.is_symlink()
    name=path.relative_to(root).as_posix()
    assert not any(s in name.lower() for s in ('private/','.ssh','password','credential','__pycache__'))
    content[name]=path.read_bytes()
for name in ('tzx_launch.c','tzx_app_boost.py','tzx_app_cache.py','tzx-app-boost.service','tzx-app-cache.service',
    'profile_app_launch.py','profile_browser_graphics.py','trial_app_launch_policy.py',
    'requalify_after_browser_probe.py','install_app_launch.py','upgrade_app_launch_readiness.py',
    'verify_app_launch_controls.py','prepare_app_launch_reboot.py','verify_app_cache_comparison.py',
    'verify_app_launch_final.py','capture_app_launch_checkpoint.py'):
    add(root/'firmware'/name)
for name in ('build_app_launch.sh','pull_app_launch_checkpoint.py','package_app_launch_source.py','tablet_ssh.py'):
    add(root/'tools'/name)
for path in (root/'build/app-launch/stage').iterdir():
    if path.is_file():add(path)
for prefix in ('app-launch-','app-cache-','browser-','desktop-slow-','panfrost-browser-','actual-browser-'):
    for path in (root/'evidence').glob(prefix+'*'):
        if path.is_file():add(path)
for name in ('APPLICATION-LAUNCH-PERFORMANCE.md','PROGRESS.md','build/app-launch-installed-checkpoint.json'):
    add(root/name)
manifest=dict(profile='TZX-A523-app-boost-preload-source-v2',boot_id=installed['boot_id'],
    installed_archive_sha256=installed['archive_sha256'],files={n:sha(b) for n,b in content.items()},
    credentials_included=False)
target=root/'build/app-launch-source-checkpoint.tar.gz';assert not target.exists()
with tarfile.open(target,'w:gz') as archive:
    for name,data in dict(content,**{'MANIFEST.json':(json.dumps(manifest,indent=2)+'\n').encode()}).items():
        item=tarfile.TarInfo(name);item.size=len(data);item.mode=0o600;archive.addfile(item,io.BytesIO(data))
with tarfile.open(target) as archive:
    members=archive.getmembers();assert len(members)==len({m.name for m in members})==len(content)+1
    for item in members:
        path=PurePosixPath(item.name);assert item.isfile() and not path.is_absolute() and '..' not in path.parts
    for name,digest in manifest['files'].items():assert sha(archive.extractfile(name).read())==digest,name
record=dict(manifest,archive_sha256=sha(target.read_bytes()),archive_bytes=target.stat().st_size,every_member_verified=True)
(root/'build/app-launch-source-checkpoint.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('APP_LAUNCH_SOURCE_EVERY_MEMBER_VERIFIED',json.dumps(dict(files=len(content),bytes=record['archive_bytes'],sha256=record['archive_sha256'])),flush=True)
