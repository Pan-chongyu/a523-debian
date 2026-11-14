"""Freeze CPU/GPU sources, exact modules, primary references and trial evidence."""
import hashlib,io,json,tarfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
wsl=Path(r'\\wsl.localhost\Ubuntu-22.04\opt\a523-debian-20261109')
content={};sha=lambda b:hashlib.sha256(b).hexdigest()
def add(path,name=None):
    path=Path(path);assert path.is_file() and not path.is_symlink(),str(path)
    name=name or path.relative_to(root).as_posix()
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    assert not any(s in name.lower() for s in ('private/','.ssh','credential','password'))
    content[name]=path.read_bytes()
keywords=('cpu_full','cpu-full','cpu_gpu','cpu-gpu','cpufreq_dvfs_v2','cpu_dvfs_cooling_v2',
          'gpu_devfreq','gpu-devfreq','gpu_compute','native_cooling','native_gpu_cooling',
          'native_panfrost','restore_hs_after_cpu')
for directory in ('firmware','tools'):
    for path in (root/directory).iterdir():
        if path.is_file() and any(s in path.name for s in keywords):add(path)
for name in ('firmware/tzx_cpu_cooling_runtime.py','firmware/linux_entry.S',
             'tools/tablet_ssh.py','tools/watch_boot.py','firmware/verify_safe_memory.py',
             'firmware/tzx_direct_io.py','CPU-GPU-FULL-INTEGRATION.md','PROGRESS.md',
             'ADVANCED-PERFORMANCE-INTEGRATION.md','build/cpu-gpu-kernel/kernel.config',
             'build/cpu-gpu-kernel/linux-bundle.json','build/cpu-gpu-kernel/Module.symvers',
             'build/cpu-gpu-kernel/linux-entry.bin','build/cpu-gpu-kernel/panfrost.ko',
             'build/cpu-gpu-runtime.tar.gz','build/cpu-gpu-native-installed-checkpoint.json',
             'build/gpu-dma32-aarch64/SOURCE.json'):
    add(root/name)
for directory in ('build/cpu-full','build/gpu-devfreq','build/cpu-gpu-kernel/panfrost-source',
                  'upstream/performance-reference'):
    for path in (root/directory).iterdir():
        if path.is_file():add(path)
for name in ('drivers/base/arch_topology.c','drivers/clk/sunxi-ng/ccu-sun55i-a523.c',
             'drivers/iommu/sun50i-iommu.c','drivers/mmc/host/sunxi-mmc.c',
             'drivers/mmc/host/tzx_emmc_host.inc','drivers/mmc/core/mmc.c',
             'drivers/mmc/core/tzx_emmc_core.inc','drivers/mmc/core/tzx_emmc_hs.h',
             'include/dt-bindings/clock/sun55i-a523-ccu.h',
             'include/dt-bindings/reset/sun55i-a523-ccu.h','Makefile'):
    add(wsl/'linux-hs-source'/name,'kernel-current/'+name)
for name in ('include/generated/compile.h','include/generated/utsrelease.h'):
    add(wsl/'kernel-hs-build'/name,'kernel-build/'+name)
evidence_prefix=('cpu-full-','cpu-gpu-','gpu-native-','native-gpu-cooling-','native-cooling-',
                 'mali-g57-es31-','mali-g57-installed-')
for path in (root/'evidence').iterdir():
    if path.is_file() and path.name.startswith(evidence_prefix):add(path)
installed=json.loads((root/'build/cpu-gpu-native-installed-checkpoint.json').read_text())
assert installed['every_member_verified'] and installed['normal_reboot_verified']
manifest=dict(profile='cpu-gpu-native-source-20261113',files={n:sha(b) for n,b in content.items()},
    installed_archive_sha256=installed['archive_sha256'],kernel_image_sha256='470dd0c350c7ef7aad392eac3a35237672862f0fffdacea8da4e6adb6740e6e4',
    full_kernel_source_included=False,cross_compiler_included=False,rootfs_included=False,
    limits=installed['limits'],note='Experiments are retained as evidence. Only installed manifests identify production files; historical initial guard trial precedes the qualified v2 revision.')
target=root/'build/cpu-gpu-native-source-checkpoint.tar.gz'
assert not target.exists()
with tarfile.open(target,'w:gz') as archive:
    for name,data in dict(content,**{'MANIFEST.json':(json.dumps(manifest,indent=2)+'\n').encode()}).items():
        member=tarfile.TarInfo(name);member.size=len(data);member.mode=0o600
        archive.addfile(member,io.BytesIO(data))
with tarfile.open(target) as archive:
    members=archive.getmembers()
    assert len(members)==len(content)+1 and {m.name for m in members}==set(content)|{'MANIFEST.json'}
    for name,digest in manifest['files'].items():assert sha(archive.extractfile(name).read())==digest,name
record=dict(manifest,archive_sha256=sha(target.read_bytes()),archive_bytes=target.stat().st_size,every_member_verified=True)
target.with_suffix('').with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('CPU_GPU_SOURCE_CHECKPOINT_ALL_MEMBERS_VERIFIED',json.dumps(dict(files=len(content),bytes=record['archive_bytes'],sha256=record['archive_sha256'])),flush=True)
