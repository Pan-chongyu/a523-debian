"""Capture the installed, reboot-qualified profile and its intact boot fallback."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time

assert os.geteuid() == 0
sha = lambda data: hashlib.sha256(data).hexdigest()
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
state = Path('/var/lib/tzx')
qualification = json.loads((state/'advanced-performance-reboot-qualified.json').read_text())
assert qualification['status'] == 'PASS' and qualification['boot_id'] == boot
assert qualification['normal_reboot_verified'] and not qualification['poweroff_key_on_verified']
assert not subprocess.check_output(['systemctl', '--failed', '--no-legend', '--plain'], text=True).strip()
subprocess.run(['python3', '/home/debian/install_hs_kernel.py', 'verify-boot'], check=True, timeout=60)
target = Path('/home/debian/advanced-performance-installed-checkpoint.tar.gz')
assert not target.exists()
content = {}
modes = {}
links = {}

def add(path):
    path = Path(path)
    assert path.is_absolute() and path.exists(), str(path)
    assert not any(word in str(path).lower() for word in ('.ssh', 'private', 'credential', 'password'))
    name = str(path).lstrip('/')
    if path.is_symlink():
        relative = os.readlink(path)
        assert not Path(relative).is_absolute() and '..' not in Path(relative).parts
        assert path.resolve().is_file()
        links[name] = relative
        return
    assert path.is_file()
    data = path.read_bytes()
    assert len(data) <= 16*1024*1024
    if name in content:
        assert content[name] == data
    content[name] = data
    modes[name] = path.stat().st_mode & 0o777

for directory in ('/usr/local/lib/tzx-cpu-dvfs', '/usr/local/lib/tzx-gpu-performance',
                  '/usr/local/lib/tzx-video', '/usr/local/lib/tzx-zram', '/usr/local/lib/tzx-emmc-hs',
                  '/usr/local/lib/tzx-cpufreq', '/usr/local/lib/tzx-cpu-cooling',
                  '/usr/local/lib/tzx-cpu-performance', '/usr/local/lib/tzx-emmc-performance',
                  '/opt/tzx-video'):
    for path in sorted(Path(directory).rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            add(path)
for path in json.loads(Path('/usr/local/lib/tzx-zram/native-installed.json').read_text()):
    add(path)
for name in ('tzx-cpu-dvfs', 'tzx-gpu-performance', 'tzx-video', 'tzx-zram', 'tzx-emmc-hs',
             'tzx-cpufreq', 'tzx-cpu-cooling', 'tzx-cpu-performance', 'tzx-emmc-performance'):
    add('/etc/systemd/system/'+name+'.service')
for path in ('/etc/sysctl.d/60-tzx-zram.conf', '/etc/udev/rules.d/70-tzx-video.rules',
             '/etc/cedarc.conf', '/usr/local/bin/tzx-video-player',
             '/usr/share/applications/tzx-video-player.desktop',
             '/etc/modprobe.d/tzx-acceleration-manual.conf'):
    add(path)
for name in ('advanced-performance-qualified', 'advanced-performance-reboot-qualified',
             'cpu-dvfs-qualified', 'cpu-dvfs-installed', 'gpu-performance-qualified',
             'gpu-performance-installed', 'emmc-hs-qualified', 'emmc-hs-installed',
             'emmc-hs-service-controls', 'video-qualified', 'video-desktop-qualified',
             'video-installed', 'zram-qualified', 'hs-kernel-v4-installed',
             'screen-boot-health', 'screen-installed', 'screen-qualified',
             'dram-gpu-boot-health', 'dram-gpu-runtime-installed'):
    add(state/(name+'.json'))
for path in ('/boot/Image', '/boot/board.dtb', '/boot/initramfs.cpio.gz',
             '/boot/kernel.config', '/boot/config-7.3.3-tzx-a523-accel1',
             '/home/debian/installed-bundle.json', '/home/debian/hs-kernel/kernel.config',
             '/home/debian/hs-kernel/linux-bundle.json', '/home/debian/hs-kernel/linux-bundle.bin',
             '/home/debian/hs-kernel/qualified-200-100.json',
             '/home/debian/hs-kernel/controls-200-100.json',
             '/root/tzx-recovery/hs-kernel-v4/active-header.bin',
             '/root/tzx-recovery/hs-kernel-v4/before.json'):
    add(path)
for path in Path('/root/tzx-recovery/hs-kernel-v4/files').rglob('*'):
    if path.is_file():
        add(path)
for name in ('install_hs_kernel.py', 'install_cpu_dvfs.py', 'install_emmc_hs_runtime.py',
             'qualify_advanced_reboot.py',
             'verify_advanced_performance.py', 'verify_emmc_hs.py',
             'verify_emmc_hs_controls.py', 'capture_advanced_checkpoint.py'):
    add(Path('/home/debian')/name)
add('/home/debian/video-stage/install_video_runtime.py')
for name in ('cpu-dvfs', 'gpu-performance', 'emmc-hs', 'zram'):
    add(Path('/run/tzx-'+name+'.json'))
add('/home/debian/video-reboot-visible.png')
add('/home/debian/video-player-result.json')

raw = {}
with Path('/dev/mmcblk0').open('rb', buffering=0) as disk:
    for name, lba, length, expected in (
        ('trained-toc0.bin', 256, 40960, '311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75'),
        ('active-header.bin', 4096, 512, '47e503b504a0b4260a3509fccad1918408058ffe47a8cbb9e9b84f7abed91d1f'),
        ('extended-recovery-slot.bin', 65536, 15008768, '091ebfe06aa47ca3a4ac7e347838dd6175c575771032e1703e6b7b1480e460e3'),
        ('hs-v4-active-slot.bin', 98304, 15008768, '2792b0e8b1087287c4e1da8f036fb3a72b11d4b5e21da7e38111d90785a6509e'),
        ('gpt-primary.bin', 0, 34*512, None),
        ('gpt-secondary.bin', 244318208-33, 33*512, None)):
        disk.seek(lba*512)
        data = disk.read(length)
        assert len(data) == length
        if expected:
            assert sha(data) == expected, name
        content['raw-emmc/'+name] = data
        modes['raw-emmc/'+name] = 0o600
        raw[name] = dict(lba=lba, bytes=length, sha256=sha(data))

for name, args in (
    ('systemd-state.txt', ['systemctl', 'status', '--no-pager', 'tzx-cpu-dvfs', 'tzx-gpu-performance', 'tzx-video', 'tzx-zram', 'tzx-emmc-hs']),
    ('current-kernel.log', ['journalctl', '-b', '-k', '--no-pager']),
    ('previous-performance-stop.log', ['journalctl', '-b', '-1', '--no-pager', '-u', 'tzx-cpu-dvfs', '-u', 'tzx-gpu-performance', '-u', 'tzx-emmc-hs']),
    ('video-reboot-observe.log', ['journalctl', '-b', '--no-pager', '-u', 'tzx-video-reboot-observe'])):
    content['evidence/'+name] = subprocess.check_output(args, timeout=30)
    modes['evidence/'+name] = 0o600

assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
manifest = dict(profile='advanced-performance-20261113', cid='3e01ff55454d20202010209170281b59',
    boot_id=boot, captured_unix=int(time.time()), normal_reboot_verified=True,
    poweroff_key_on_verified=False, rootfs_backup=False, raw_boot_readback=raw,
    files={name:sha(data) for name, data in content.items()}, modes=modes, symlinks=links,
    paired_baseline=dict(file='screen-poweron-installed-scoped-checkpoint.tar.gz',
        sha256='618213cdbc7b0f22988b0b705f111a0d4a1887bfc3452c1ee2afa10ea28a3bc8'),
    limits=qualification['limits'],
    restore_note='Scoped files and actual boot areas only. Preserve modes and recreate the recorded relative symlinks. Do not write the full archive to eMMC. The board-pinned installer can select the intact extended recovery slot after disabling tzx-emmc-hs.service.')
with tarfile.open(target, 'w:gz') as archive:
    for name, data in dict(content, **{'MANIFEST.json':(json.dumps(manifest, indent=2)+'\n').encode()}).items():
        entry = tarfile.TarInfo(name)
        entry.mode = modes.get(name, 0o600)
        entry.size = len(data)
        archive.addfile(entry, io.BytesIO(data))
target.chmod(0o644)
print('ADVANCED_INSTALLED_CHECKPOINT_CREATED', json.dumps(dict(path=str(target),
    bytes=target.stat().st_size, sha256=sha(target.read_bytes()), files=len(content))), flush=True)
