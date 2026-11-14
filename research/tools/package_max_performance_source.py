"""Freeze the exact performance sources and their real hardware evidence."""
import hashlib,io,json,tarfile
from pathlib import Path,PurePosixPath
root=Path(__file__).resolve().parents[1]
installed=json.loads((root/'build/max-performance-installed-checkpoint.json').read_text(encoding='utf-8'))
assert installed['every_member_verified']
sha=lambda data:hashlib.sha256(data).hexdigest();content={}
def add(path):
    path=Path(path);assert path.is_file() and not path.is_symlink()
    name=path.relative_to(root).as_posix()
    assert not any(value in name.lower() for value in ('private/','.ssh','password','credential','__pycache__'))
    content[name]=path.read_bytes()
for name in ('tzx_performance_mode.py','tzx-cpu-performance-mode.service','install_performance_mode.py',
    'tzx_cpu_early_performance_runtime.py','tzx_early_performance_check.py','tzx-early-performance-check.service',
    'tzx-early-cpu-performance.conf','tzx_gpu_max_performance_runtime.py','tzx_gpu_max_performance_startup.py',
    'upgrade_early_performance.py','boot_cpu_performance.c','install_boot_cpu_performance.py',
    'verify_boot_cpu_performance.py','verify_performance_mode.py','verify_max_performance_caps.py',
    'capture_max_performance_checkpoint.py','profile_app_launch.py','profile_browser_graphics.py',
    'requalify_after_browser_probe.py','verify_cpu_gpu_integration.py','verify_boot_panel_native_stack.py'):
    add(root/'firmware'/name)
for name in ('prepare_early_performance.py','build_boot_cpu_performance.sh','compose_boot_cpu_performance.py',
    'verify_boot_cpu_performance_emulation.py','prepare_boot_cpu_performance_files.py',
    'pull_max_performance_checkpoint.py','package_max_performance_source.py','make_toc0.py'):
    add(root/'tools'/name)
for directory in ('boot-cpu-performance','performance-mode-base'):
    for path in (root/'build'/directory).iterdir():
        if path.is_file():add(path)
for prefix in ('performance-mode-','boot-cpu-performance-','app-launch-','browser-','desktop-slow-'):
    for path in (root/'evidence').glob(prefix+'*'):
        if path.is_file():add(path)
for name in ('APPLICATION-LAUNCH-PERFORMANCE.md','PROGRESS.md','build/max-performance-installed-checkpoint.json'):
    add(root/name)
manifest=dict(profile='TZX-A523-early-max-performance-no-preload-source',boot_id=installed['boot_id'],
    installed_archive_sha256=installed['archive_sha256'],files={name:sha(data) for name,data in content.items()},credentials_included=False)
target=root/'build/max-performance-source-checkpoint.tar.gz';assert not target.exists()
with tarfile.open(target,'w:gz') as archive:
    for name,data in dict(content,**{'MANIFEST.json':(json.dumps(manifest,indent=2)+'\n').encode()}).items():
        member=tarfile.TarInfo(name);member.size=len(data);member.mode=0o600;archive.addfile(member,io.BytesIO(data))
with tarfile.open(target) as archive:
    members=archive.getmembers();assert len(members)==len({m.name for m in members})==len(content)+1
    for member in members:
        name=PurePosixPath(member.name);assert member.isfile() and not name.is_absolute() and '..' not in name.parts
    for name,digest in manifest['files'].items():assert sha(archive.extractfile(name).read())==digest,name
record=dict(manifest,archive_sha256=sha(target.read_bytes()),archive_bytes=target.stat().st_size,every_member_verified=True)
(root/'build/max-performance-source-checkpoint.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('MAX_PERFORMANCE_SOURCE_EVERY_MEMBER_VERIFIED',json.dumps(dict(files=len(content),bytes=record['archive_bytes'],sha256=record['archive_sha256'])),flush=True)
