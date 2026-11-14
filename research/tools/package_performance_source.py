"""Freeze this performance revision, paired with the actual installed snapshot."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--storage',action='store_true')
args = parser.parse_args()
actual_stem = 'performance-storage-installed-checkpoint' if args.storage else 'performance-installed-checkpoint'
source_stem = 'performance-storage-source-checkpoint' if args.storage else 'performance-source-checkpoint'
actual = json.loads((root/('build/'+actual_stem+'.json')).read_text())
assert actual['every_member_verified'] and actual['physical_reboot_tested'] == args.storage
actual_archive = root/('build/'+actual_stem+'.tar.gz')
assert hashlib.sha256(actual_archive.read_bytes()).hexdigest() == actual['archive_sha256']
sources = {
    'PERFORMANCE-INTEGRATION.md', 'PROGRESS.md', 'tools/package_performance_source.py',
    'firmware/tzx_cpufreq_safepll.c', 'firmware/tzx_cpu_cooling.c',
    'firmware/cpu_frequency_workload.c', 'firmware/cpu_execution_coherency.c',
    'firmware/memory_check.c', 'firmware/verify_safe_memory.py',
    'build/memory-check-bounded', 'build/cpufreq-framework-kernel/cpu-frequency-workload',
    'build/wifi-bus-trial/tzx_wifi_runtime.c',
    'build/performance-installed-checkpoint.json',
    'tools/wifi_benchmark_server.py', 'tools/tablet_ssh.py', 'tools/fel_device.py',
    'tools/build_cpufreq_framework_kernel.sh', 'tools/build_screen_boot_kernel.sh',
}
if args.storage:
    sources.update({'EMMC-PERFORMANCE-INTEGRATION.md', 'build/'+actual_stem+'.json',
                    'firmware/verify_emmc_production.py','firmware/qualify_storage_reboot.py'})
# Only this task's sources, generated artifacts and primary references. No
# recursive project archive: credentials, unrelated images and rootfs stay out.
for directory, pattern in (('firmware', '*performance*'), ('tools', '*performance*'),
                           ('evidence', '*performance*.txt')):
    sources.update(p.relative_to(root).as_posix() for p in (root/directory).glob(pattern) if p.is_file())
for directory in ('build/cpu-performance', 'build/gpu-performance',
                  'build/wifi-performance', 'upstream/performance-reference'):
    sources.update(p.relative_to(root).as_posix() for p in (root/directory).rglob('*') if p.is_file())
if args.storage:
    sources.update(p.relative_to(root).as_posix() for p in (root/'build/emmc-performance').rglob('*') if p.is_file())
for kind in (('cpu','gpu','emmc') if args.storage else ('cpu','gpu')):
    package = json.loads((root/('build/'+kind+'-performance/manifest.json')).read_text())
    for path, digest in package['files'].items():
        assert actual['files'][path.lstrip('/')] == digest, path
assert hashlib.sha256((root/'build/cpu-performance/source/tzx_cpufreq_safepll.c').read_bytes()).digest() == hashlib.sha256((root/'firmware/tzx_cpufreq_safepll.c').read_bytes()).digest()
content = {}
for name in sorted(sources):
    path = root/name
    assert path.is_file() and not path.is_symlink(), name
    assert not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts
    assert not any(word in name.lower() for word in ('private/', 'password', 'credential', '__pycache__'))
    content[name] = path.read_bytes()
manifest = {
    'profile': actual['profile'], 'cid': actual['cid'],
    'boot_id': actual['boot_id'], 'physical_reboot_tested': args.storage,
    'normal_reboot_verified': args.storage, 'poweroff_key_on_verified': False,
    'actual_installed_checkpoint': actual_archive.name,
    'actual_installed_checkpoint_sha256': actual['archive_sha256'],
    'paired_screen_source': 'dram-boot-voltage-screen-poweron-checkpoint.tar.gz',
    'paired_screen_source_sha256': 'e72c840be5041f48a03227302b3bfd12e0ded42d159d46a4d9e0de8a798cd878',
    'scope': 'This revision sources, generated modules, exact manifests, trials and references; no rootfs or keys',
    'build_environment': 'WSL Ubuntu-22.04; /opt/a523-debian-20261109/linux-7.3.3; kernel-cpufreq-framework-build; aarch64-linux-gnu-gcc 11.4',
    'files': {n: hashlib.sha256(data).hexdigest() for n,data in content.items()}}
target = root/('build/'+source_stem+'.tar.gz')
with target.open('xb') as stream:
    with tarfile.open(fileobj=stream, mode='w:gz') as archive:
        for name,data in dict(content, **{'MANIFEST.json': (json.dumps(manifest, indent=2)+'\n').encode()}).items():
            member = tarfile.TarInfo(name)
            member.mode, member.size = 0o600, len(data)
            archive.addfile(member, io.BytesIO(data))
with tarfile.open(target) as archive:
    assert len(archive.getnames()) == len(content)+1
    assert set(archive.getnames()) == set(content) | {'MANIFEST.json'}
    for name,digest in manifest['files'].items():
        assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == digest, name
record = dict(manifest, archive_bytes=target.stat().st_size,
              archive_sha256=hashlib.sha256(target.read_bytes()).hexdigest(), every_member_verified=True)
(root/('build/'+source_stem+'.json')).write_text(json.dumps(record, indent=2)+'\n')
print('PERFORMANCE_SOURCE_CHECKPOINT_EVERY_MEMBER_VERIFIED', json.dumps({
    'files': len(content), 'bytes': record['archive_bytes'], 'sha256': record['archive_sha256']}))
