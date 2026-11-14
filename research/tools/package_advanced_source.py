"""Freeze reviewable current sources, exact artifacts, and qualification evidence."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
wsl = Path(r'\\wsl.localhost\Ubuntu-22.04\opt\a523-debian-20261109')
content = {}
sha = lambda data: hashlib.sha256(data).hexdigest()

def add(path, name=None):
    path = Path(path)
    assert path.is_file() and not path.is_symlink(), str(path)
    name = name or path.relative_to(root).as_posix()
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    assert not any(word in name.lower() for word in ('.ssh', 'private/', 'credential', 'password'))
    content[name] = path.read_bytes()

keywords = ('advanced', 'cpu_dvfs', 'cpu-dvfs', 'cpufreq_dvfs', 'emmc_hs', 'emmc-hs',
            'hs_kernel', 'extended_kernel', 'extended_bundle', 'video', 'zram', 'cedar',
            'emmc_transition_guard', 'tzx_emmc_core', 'tzx_emmc_host', 'requalify_after_emmc')
for directory in ('firmware', 'tools'):
    for path in (root/directory).iterdir():
        if path.is_file() and any(word in path.name for word in keywords):
            add(path)
for name in ('firmware/linux_entry.S', 'firmware/tzx_cpufreq_safepll.c',
             'firmware/tzx_cpu_performance_runtime.py', 'firmware/tzx_cpu_perf_cooling.c',
             'firmware/tzx-cpu-performance.service', 'firmware/tzx_cpu_cooling.c',
             'firmware/tzx-gpu-performance.service', 'firmware/tzx_gpu_performance_runtime.py',
             'tools/fetch_extended_performance_reference.py', 'tools/audit_extended_module_code.py',
             'tools/compose_hs_bundle.py', 'tools/prepare_hs_installer.py',
             'ADVANCED-PERFORMANCE-INTEGRATION.md'):
    path = root/name
    if path.is_file():
        add(path)
for directory in ('build/cpu-dvfs', 'build/hs-kernel', 'build/extended-kernel/native'):
    for path in (root/directory).rglob('*'):
        if path.is_file() and path.suffix in ('.c', '.h', '.ko', '.config'):
            add(path)
for name in ('build/hs-kernel/linux-bundle.json', 'build/hs-kernel/kernel.config',
             'build/hs-kernel/linux-entry.bin', 'build/hs-kernel/emmc-transition-guard',
             'build/extended-kernel/linux-bundle.json', 'build/extended-kernel/kernel.config',
             'build/extended-kernel/board.dts', 'build/extended-kernel/board.dtb',
             'build/extended-kernel/Module.symvers', 'build/extended-kernel/module-audit/complete.json',
             'build/extended-kernel/verify-zram', 'build/video/sunxi-ve.ko',
             'build/video/tzx_video_nodes.ko', 'build/video/userspace.tar.gz',
             'build/video/video-reboot-visible.png', 'downloads/cedar-userspace/SOURCES.json',
             'downloads/video-debian/manifest.json'):
    add(root/name)
for directory in ('upstream/performance-reference', 'upstream/mmc-vendor'):
    for path in (root/directory).iterdir():
        if path.is_file():
            add(path)
for name in ('drivers/mmc/host/sunxi-mmc.c', 'drivers/mmc/host/tzx_emmc_host.inc',
             'drivers/mmc/core/mmc.c', 'drivers/mmc/core/tzx_emmc_core.inc',
             'drivers/mmc/core/tzx_emmc_hs.h', 'drivers/iommu/sun50i-iommu.c',
             'drivers/clk/sunxi-ng/ccu-sun55i-a523.c',
             'include/dt-bindings/clock/sun55i-a523-ccu.h',
             'include/dt-bindings/reset/sun55i-a523-ccu.h', 'Makefile'):
    add(wsl/'linux-hs-source'/name, 'kernel-current/'+name)
for name in ('include/generated/compile.h', 'include/generated/utsrelease.h'):
    add(wsl/'kernel-hs-build'/name, 'kernel-build/'+name)
cedar = wsl/'vpu-cedar-port/drivers/media/platform/sunxi/cedar-ve'
for path in cedar.iterdir():
    if path.suffix in ('.c', '.h', '.S') and '.mod.' not in path.name or path.name in ('Kconfig', 'Makefile'):
        add(path, 'cedar-ve-source/'+path.name)
evidence = ('cpu-dvfs-complete.txt', 'cpu-dvfs-install.txt', 'zram-qualification-install.txt',
    'video-decode-both.txt', 'video-decode-1080p.txt', 'video-steady-throughput.txt',
    'emmc-v4-hs200-100-trial.txt', 'emmc-v4-hs400-100-trial.txt', 'hs-v4-hs400-kernel-live.txt',
    'emmc-hs200-lease-expiry-controls.txt', 'hs200-service-controls-final-install.txt',
    'advanced-combined-performance.txt', 'advanced-reboot-coexistence.txt',
    'advanced-video-zram-file-final-check.txt', 'advanced-normal-reboot-final-qualification.txt',
    'advanced-final-reboot-watch.json', 'advanced-final-reboot-first-status.txt',
    'advanced-final-reboot-file-audit.txt', 'advanced-post-checkpoint-system-health.txt',
    'advanced-performance-installed-checkpoint-capture.txt',
    'advanced-checkpoint-usb-disconnect-status.txt')
for name in evidence:
    add(root/'evidence'/name)
manifest = dict(profile='advanced-performance-source-20261113',
    files={name:sha(data) for name,data in content.items()},
    installed_archive_sha256='16cd5bc7b43ab16dbeab21a2718e366e3365e2d5e48bfce19a339e342cf3b7c3',
    kernel_base='Linux 7.3.3 with the existing A523 board baseline; current changed files included',
    full_kernel_source_included=False, cross_compiler_included=False, rootfs_included=False,
    current_Image_sha256='4c47d5cf91a544b0c9d47901309b0bca8e8ff71320f91a4088da37ab565615fc',
    limits=['HS400 and HS200 above 100MHz are unqualified',
            'X11 desktop playback still drops frames', 'No browser hardware decoding integration',
            'No physical poweroff/key-on test for this combination',
            'Source generators include experiments; only actual installed manifests define production files'])
target = root/'build/advanced-performance-source-checkpoint.tar.gz'
if target.exists():
    # Only replace our own named generated archive, never arbitrary paths.
    with tarfile.open(target) as previous:
        old_manifest = json.load(previous.extractfile('MANIFEST.json'))
        assert old_manifest['profile'] == manifest['profile']
with tarfile.open(target, 'w:gz') as archive:
    for name,data in dict(content, **{'MANIFEST.json':(json.dumps(manifest,indent=2)+'\n').encode()}).items():
        entry = tarfile.TarInfo(name)
        entry.mode = 0o600
        entry.size = len(data)
        archive.addfile(entry, io.BytesIO(data))
with tarfile.open(target) as archive:
    members = archive.getmembers()
    assert len(members) == len(content)+1
    assert {m.name for m in members} == set(content)|{'MANIFEST.json'}
    for name,digest in manifest['files'].items():
        assert sha(archive.extractfile(name).read()) == digest
record = dict(manifest, archive_sha256=sha(target.read_bytes()), archive_bytes=target.stat().st_size,
              every_member_verified=True)
target.with_suffix('').with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n', encoding='utf-8')
print('ADVANCED_SOURCE_CHECKPOINT_ALL_MEMBERS_VERIFIED',json.dumps(dict(
    files=len(content),bytes=record['archive_bytes'],sha256=record['archive_sha256'])),flush=True)
