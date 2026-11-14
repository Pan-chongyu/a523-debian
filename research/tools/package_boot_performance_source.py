"""Freeze the qualified boot delta, its build inputs and hardware evidence."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

root = Path(__file__).resolve().parents[1]
sha = lambda b: hashlib.sha256(b).hexdigest()
installed_path = root/'build/boot-performance-installed-checkpoint-v2.tar.gz'
installed = json.loads(installed_path.with_suffix('').with_suffix('.json').read_text())
assert installed['every_member_verified'] and installed['poweroff_key_on_verified']
assert sha(installed_path.read_bytes()) == installed['archive_sha256']
boot = '552e50af-434d-4ef7-8206-46b6d77202ca'
normal = 'e6cf9178-a7c0-410e-86aa-d534ce52e0fa'
pin = '50537c7ff9d9b20461c0a1181f3b4f04240e63be7aece9f49ba1ce6c18bc0c9b'
with tarfile.open(installed_path) as archive:
    proof_bytes = archive.extractfile('var/lib/tzx/fast-boot-key-on-qualified.json').read()
    proof = json.loads(proof_bytes)
    assert proof['status'] == 'PASS' and proof['boot_id'] == boot
    assert proof['previous_boot_id'] == normal and proof['toc0_sha256'] == pin
    assert proof['cold_boot_proof']['verification_method'] == 'PMIC-key-on'
    assert proof['normal_reboot_proof']['verification_method'] == 'normal-reboot'
    assert proof['visual_confirmation']['physical_key_to_visible_screen_seconds_approx'] == 31
    current_order = json.load(archive.extractfile('var/lib/tzx/boot-latency-installed.json'))
    assert current_order['poweroff_key_on_boot_id'] == boot and current_order['normal_reboot_boot_id'] == normal
    (root/'evidence/boot-hwcrc-final-key-on-proof.json').write_bytes(proof_bytes)
    (root/'evidence/boot-hwcrc-key-on-hardware-timing.txt').write_bytes(archive.extractfile('evidence/boot-profile.txt').read())

# The immutable installed archive retains the manifests as they were deployed.
# These host build manifests receive a separate, evidence-linked hardware attestation.
stages = (
    ('boot-latency-loader', '91294d8e-9cab-43b8-9a38-4cab9e1cc2d5', 'boot-fast-crc-qualified.txt'),
    ('boot-early-cpub', '33abd034-d5c4-477b-ae73-a3dcce04f586', 'boot-early-cpub-qualified-restored-cpu.txt'),
    ('boot-profile', '78671de4-bd01-412b-8e22-45551d8b940e', 'boot-profile-qualified.txt'),
    ('boot-fast', '3e7af45a-da37-46e9-b348-73feeb55f130', 'boot-fast-pins-word-qualified.txt'),
    ('boot-hwcrc', normal, 'boot-hwcrc-normal-qualified.txt'),
)
for stage, verified_boot, evidence in stages:
    path = root/'build'/stage/'loader.toc0.json'
    value = json.loads(path.read_text())
    assert sha(path.with_suffix('').read_bytes()) == value['image_sha256']
    log = (root/'evidence'/evidence).read_text(encoding='utf-8')
    assert verified_boot in log and 'BOOT_LATENCY_AND_UNCHANGED_NATIVE_STACK_PASS' in log
    value.update(hardware_boot_verified=True, hardware_boot_id=verified_boot,
                 hardware_evidence='evidence/'+evidence,
                 hardware_evidence_sha256=sha((root/'evidence'/evidence).read_bytes()),
                 installed_status='current' if stage == 'boot-hwcrc' else 'superseded',
                 host_attestation_after_deployment=True)
    if stage == 'boot-hwcrc':
        value.update(poweroff_key_on_verified=True, poweroff_key_on_boot_id=boot,
                     poweroff_key_on_evidence_sha256=sha(proof_bytes),
                     user_black_screen_seconds_approx=28, user_power_key_to_display_seconds_approx=31)
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
for stage, tested_boot, reason, evidence in (
    ('boot-wide-emmc', 'f1acdc31-20e8-480d-8a19-c351ec39d232',
     'Booted using protected one-bit fallback; missing data pins; candidate withdrawn.',
     'boot-wide-exact-rollback.txt'),
    ('boot-icache', '096bf8cc-2882-4da4-a626-43680333d3a4',
     'Existing instruction cache was already enabled; hook skipped; candidate withdrawn.',
     'boot-icache-rollback-and-CRC-feature.txt'),
):
    path = root/'build'/stage/'loader.toc0.json'
    value = json.loads(path.read_text())
    assert sha(path.with_suffix('').read_bytes()) == value['image_sha256']
    value.update(hardware_boot_verified=False, installed_status='withdrawn',
                 hardware_test_boot_id=tested_boot, hardware_test_result=reason,
                 rollback_evidence='evidence/'+evidence,
                 host_attestation_after_deployment=True)
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')

for name in ('BOOT-LATENCY-INTEGRATION.md', 'CPU-GPU-FULL-INTEGRATION.md', 'PROGRESS.md'):
    path = root/name
    text = path.read_text(encoding='utf-8')
    text = text.replace('build/boot-performance-installed-checkpoint.tar.gz',
                        'build/boot-performance-installed-checkpoint-v2.tar.gz')
    text = text.replace('526875', str(installed['archive_bytes']))
    text = text.replace('c59b46b8345778b250f48b3cee67351d70241975d80ed6a9e9bd228fa7ecdf69',
                        installed['archive_sha256'])
    path.write_text(text, encoding='utf-8')

content = {}
def add(path):
    path = Path(path)
    assert path.is_file() and not path.is_symlink(), path
    name = path.relative_to(root).as_posix()
    assert not any(s in name.lower() for s in ('private/', '.ssh', 'credential', 'password', '__pycache__'))
    assert path.stat().st_size < 2*1024*1024, path
    content[name] = path.read_bytes()

for directory in ('firmware', 'tools'):
    patterns = ('boot_*.c', 'install_boot_*.py', 'verify_boot_*.py', 'read_boot_profile.py',
                'build_boot_*.sh', 'compose_boot_*.py', 'prepare_boot_*_installer.py',
                '*boot*checkpoint.py', 'package_boot_performance_source.py',
                'fix_performance_shutdown.py', 'prepare_fast_boot_key_on.py',
                'qualify_fast_boot_key_on.py', 'finalize_boot_user_validation.py')
    for pattern in patterns:
        for path in (root/directory).glob(pattern):
            # Filesystem/image builders belong to earlier checkpoints, not this delta.
            if path.name not in ('build_boot_image.sh',):
                add(path)
for name in ('tools/make_toc0.py', 'tools/fel_device.py', 'tools/tablet_ssh.py', 'tools/watch_boot.py',
             'tools/test_dram_boot_voltage_emulation.py', 'tools/build_dram_boot_voltage_hook.sh',
             'tools/compose_dram_boot_voltage.py', 'firmware/dram_boot_voltage_hook.c',
             'evidence/initial-fel/toc0-descriptor.bin',
             'BOOT-LATENCY-INTEGRATION.md', 'CPU-GPU-FULL-INTEGRATION.md', 'PROGRESS.md',
             'DISPLAY-INTEGRATION.md', 'POWER-OFF-COLD-BOOT.md',
             'build/boot-performance-installed-checkpoint-v2.json'):
    add(root/name)
for directory in ('boot-latency-loader', 'boot-early-cpub', 'boot-wide-emmc', 'boot-profile',
                  'boot-fast', 'boot-icache', 'boot-hwcrc', 'known-good-loader', 'dram-boot-voltage'):
    for path in (root/'build'/directory).iterdir():
        if path.is_file():
            add(path)
for path in (root/'evidence').iterdir():
    if path.is_file() and path.name.startswith(('boot-', 'performance-clean-shutdown-',
                                              'performance-shutdown-race-', 'cpu-gpu-physical-key-on-')):
        add(path)
manifest = dict(profile='boot-performance-source-20261113', boot_id=boot,
    installed_delta_sha256=installed['archive_sha256'],
    paired_CPU_GPU_source_sha256='30347ef51009a6ec02bfcacbdf4337fc5aa1d734f60ce2ab4484496faf6ea1da',
    toc0_sha256=pin, files={name: sha(data) for name, data in content.items()},
    full_kernel_source_included=False, cross_compiler_included=False,
    signing_private_key_included=False, rootfs_included=False,
    note='Exact boot chain inputs and signed binaries; source rebuilds require local signing setup. '
         'Only hwcrc is current; wide/icache are withdrawn experiments. '
         'Installed archive preserves pre-test deployment manifests; host build manifests add hardware attestations. '
         'Scope of cold boot is PMIC power-off followed by the physical key with battery/USB connected.')
target = root/'build/boot-performance-source-checkpoint.tar.gz'
assert not target.exists()
with tarfile.open(target, 'w:gz') as archive:
    for name, data in dict(content, **{'MANIFEST.json': (json.dumps(manifest, indent=2)+'\n').encode()}).items():
        item = tarfile.TarInfo(name)
        item.size = len(data)
        item.mode = 0o600
        archive.addfile(item, io.BytesIO(data))
with tarfile.open(target) as archive:
    members = archive.getmembers()
    assert len(members) == len({m.name for m in members}) == len(content)+1
    assert {m.name for m in members} == set(content)|{'MANIFEST.json'}
    for item in members:
        p = PurePosixPath(item.name)
        assert item.isfile() and not p.is_absolute() and '..' not in p.parts
    for name, digest in manifest['files'].items():
        assert sha(archive.extractfile(name).read()) == digest, name
record = dict(manifest, archive_sha256=sha(target.read_bytes()),
              archive_bytes=target.stat().st_size, every_member_verified=True)
target.with_suffix('').with_suffix('.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
print('BOOT_PERFORMANCE_SOURCE_CHECKPOINT_ALL_MEMBERS_VERIFIED', json.dumps(dict(
    files=len(content), bytes=record['archive_bytes'], sha256=record['archive_sha256'])), flush=True)
