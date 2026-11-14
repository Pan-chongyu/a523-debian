"""Durable, reversible GPU startup after both full-memory comparison boots."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

p = argparse.ArgumentParser()
p.add_argument('--enable-for-reboot', action='store_true')
p.add_argument('--restore', action='store_true')
a = p.parse_args()
assert not (a.enable_for_reboot and a.restore)
assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
sha = lambda data: hashlib.sha256(data).hexdigest()
root = Path('/root/tzx-recovery/dram-gpu-runtime')
state = Path('/var/lib/tzx/dram-gpu-runtime-installed.json')
marker = Path('/var/lib/tzx/gpu-qualified')


def syncdir(path):
    fd = os.open(path, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)


def atomic(path, data, permissions=0o600):
    assert not path.is_symlink(), path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.dram-gpu-new')
    with temporary.open('wb') as f:
        f.write(data)
        f.flush()
        os.fchmod(f.fileno(), permissions)
        os.fchown(f.fileno(), 0, 0)
        os.fsync(f.fileno())
    temporary.replace(path)
    syncdir(path.parent)
    assert path.read_bytes() == data, path


def jsonwrite(path, value):
    atomic(path, json.dumps(value, indent=2).encode()+b'\n')


def run(*command, timeout=45):
    return subprocess.run(command, check=True, timeout=timeout, text=True, capture_output=True).stdout.strip()


if a.restore:
    installed = json.loads((root/'installed-files.json').read_text())
    before = json.loads((root/'before.json').read_text())
    for name, digest in installed.items():
        path = Path('/')/name
        assert not path.is_symlink() and sha(path.read_bytes()) == digest, path
    if marker.exists():
        atomic(root/'qualification-before-restore.json', marker.read_bytes())
        marker.unlink()
        syncdir(marker.parent)
    run('systemctl', 'disable', '--now', 'tzx-dram-gpu-health.service')
    run('systemctl', 'stop', 'lightdm')
    run('systemctl', 'stop', 'tzx-gpu.service')
    if Path('/sys/module/panfrost').exists():
        run('modprobe', '-r', 'panfrost')
    run('systemctl', 'stop', 'tzx-display.service')
    for name in installed:
        path = Path('/')/name
        previous = before[name]
        if previous is None:
            path.unlink()
            syncdir(path.parent)
        else:
            data = (root/'files'/name).read_bytes()
            assert sha(data) == previous['sha256']
            atomic(path, data, previous['mode'])
    pending = Path('/var/lib/tzx/dram-gpu-boot-pending.json')
    if pending.exists():
        pending.unlink()
        syncdir(pending.parent)
    run('systemctl', 'daemon-reload')
    run('systemctl', 'start', 'tzx-display.service')
    run('systemctl', 'start', 'lightdm')
    jsonwrite(state, {'state': 'restored_software_display', 'supply_boot_hook_retained': True})
    print('DRAM_GPU_STARTUP_REMOVED_SOFTWARE_DESKTOP_RESTORED', flush=True)
    raise SystemExit(0)

assert not marker.exists() and not Path('/sys/module/panfrost').exists()
assert not Path('/sys/module/tzx_cpufreq_divider').exists()
subprocess.run(['python3', '/home/debian/run_dram_boot_copy_trial.py', '--verify-only'], check=True, timeout=40)
first = json.loads(Path('/var/lib/tzx/dram-boot-first-pass.json').read_text())
assert first['state'] == 'first_boot_bounded_tests_passed_warm_boot_pending'
assert first['copies_high_and_natural_600_seconds'] == 110385 and first['full_4GiB']
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert first['boot_id'] != boot
proof = {}
for unit, markers in [
    ('tzx-dram-boot-copy-after-reboot.service', ['LIBRARY_FIXED_COPY_PASS', 'seconds_per_phase=300']),
    ('tzx-dram-boot-reboot-files-before-gpu.service', ['MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS']),
    ('tzx-dram-boot-gpu-autosuspend.service', ['DRAM_BOOT_GPU_EIGHT_ACTUAL_IDLE_RESUME_PIXEL_TESTS_PASS',
        'GPU_FULL_X11_WITH_4_SCENES_AND_THREE_2560MIB_CPU_MEMORY_PASSES',
        'GPU_CLOCKFIX_TWO_FULL_SCENE_PASSES', 'GPU_FULL_COMBINED_AND_RESIDENT_LIBRARY_GUARD_PASS',
        'DRAM_BOOT_1260_GPU_CLEANUP_SOFTWARE_DESKTOP_AND_FILE_AUDIT_PASS']),
]:
    properties = run('systemctl', 'show', unit, '-p', 'Result', '-p', 'ActiveState', '-p', 'ExecMainStatus')
    assert all(s in properties for s in ('Result=success', 'ActiveState=inactive', 'ExecMainStatus=0')), properties
    journal = run('journalctl', '-b', '-u', unit, '-o', 'cat', '--no-pager')
    assert all(s in journal for s in markers), unit
    assert not any(s in journal for s in ('MISMATCH', 'Traceback', 'CORRUPTION')), unit
    proof[unit] = sha(journal.encode())
assert sha(Path('/usr/local/lib/tzx-accel-display/tzx-display-runtime').read_bytes()) == '8581c7f3367afb0bbf117332a070622240e64cde2c404389c3f2f765956d49da'
assert sha(Path('/usr/local/lib/tzx-accel/overrides.json').read_bytes()) == '824e4ce883d9b37504af539e94a9fa000d1e1d69e551e88f08c9f51da7ed56f8'
fd = os.open('/dev/mmcblk0', os.O_RDONLY)
try:
    assert sha(os.pread(fd, 14876672, 65536*512)) == '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
finally:
    os.close(fd)
package = Path('/home/debian/dram-gpu-runtime.tar.gz').read_bytes()
assert sha(package) == 'd368813210bf1e12221e3377899ec845d9fe08231b1449bad8df4bb775a2a440'
with tarfile.open(fileobj=io.BytesIO(package), mode='r:gz') as archive:
    members = archive.getmembers()
    assert len(members) == 12 and len({m.name for m in members}) == 12
    assert all(m.isfile() and not PurePosixPath(m.name).is_absolute() and '..' not in PurePosixPath(m.name).parts and m.size < 2000000 for m in members)
    manifest = json.load(archive.extractfile('FILES.json'))
    assert {m.name for m in members} == set(manifest) | {'FILES.json'}
    files = {name: archive.extractfile(name).read() for name in manifest}
for name, data in files.items():
    assert sha(data) == manifest[name]
    assert name.startswith(('usr/local/lib/tzx-dram-gpu/', 'etc/systemd/system/'))
    if name.endswith('.py'):
        compile(data, name, 'exec')
print('DRAM_GPU_REPEAT_AND_PACKAGE_PREFLIGHT_PASS', json.dumps({'boot_id': boot, 'files': len(files), 'proof': proof}), flush=True)
if not a.enable_for_reboot:
    raise SystemExit(0)
assert not root.exists()
root.mkdir(parents=True)
syncdir(root.parent)
before = {}
for name in files:
    path = Path('/')/name
    assert not path.is_symlink()
    if path.exists():
        data = path.read_bytes()
        atomic(root/'files'/name, data)
        before[name] = {'sha256': sha(data), 'mode': path.stat().st_mode & 0o777}
    else:
        before[name] = None
jsonwrite(root/'before.json', before)
jsonwrite(root/'installed-files.json', manifest)
atomic(root/'installer.py', Path(__file__).read_bytes())
atomic(root/'runtime-package.tar.gz', package)
for name, data in files.items():
    atomic(Path('/')/name, data, 0o644)
run('systemd-analyze', 'verify', '/etc/systemd/system/tzx-dram-gpu-health.service', '/etc/systemd/system/tzx-dram-gpu-fallback.service')
run('systemctl', 'daemon-reload')
run('python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard')
profile = {'profile': 'dram-trained-1260-full4g-dma32-aarch64', 'manual_trials_passed': True,
           'state': 'two_boots_bounded_trials_passed_autostart_reboot_pending',
           'validated_manual_boot_ids': [first['boot_id'], boot], 'proof_journal_sha256': proof,
           'files': manifest, 'cpu_frequency_for_qualification_kHz': 480000}
jsonwrite(marker, profile)
run('systemctl', 'enable', 'tzx-gpu.service', 'tzx-dram-gpu-health.service')
jsonwrite(state, {'state': 'installed_autostart_reboot_pending', 'boot_id': boot, 'files': manifest})
os.sync()
print('DRAM_GPU_STARTUP_INSTALLED_REBOOT_PENDING', json.dumps(profile), flush=True)
run('systemd-run', '--unit=tzx-dram-gpu-autostart-reboot', '--on-active=3s', '/usr/bin/systemctl', 'reboot')
