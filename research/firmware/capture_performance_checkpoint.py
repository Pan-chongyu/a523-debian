"""Capture actual installed performance files, rollback originals and proof."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

assert os.geteuid() == 0
parser = argparse.ArgumentParser()
parser.add_argument('--storage', action='store_true')
args = parser.parse_args()
CID = Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()
assert CID == '3e01ff55454d20202010209170281b59'
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
validation_name = 'emmc-performance-validation-reboot.json' if args.storage else 'performance-installed-validation.json'
validation = json.loads((Path('/var/lib/tzx')/validation_name).read_text())
assert validation['status'] == 'PASS' and validation['boot_id'] == BOOT
assert not subprocess.check_output(['systemctl', '--failed', '--no-legend', '--plain'], text=True).strip()
paths = set()
for directory in ('/usr/local/lib/tzx-gpu-performance', '/usr/local/lib/tzx-cpu-performance',
                  '/usr/local/lib/tzx-cpufreq', '/usr/local/lib/tzx-cpu-cooling'):
    paths.update(p for p in Path(directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
if args.storage:
    for directory in ('/usr/local/lib/tzx-emmc-performance', '/home/debian/emmc-performance'):
        paths.update(p for p in Path(directory).rglob('*') if p.is_file() and p.suffix != '.bin' and '__pycache__' not in p.parts)
    paths.add(Path('/etc/systemd/system/tzx-emmc-performance.service'))
    for name in ('emmc-performance-installed.json','emmc-performance-qualified.json',
                 'emmc-performance-validation-online.json','emmc-performance-validation-reboot.json',
                 'performance-reboot-qualified.json','performance-storage-reboot-qualified.json'):
        paths.add(Path('/var/lib/tzx')/name)
    for name in ('qualify_performance_reboot.py','verify_emmc_performance.py','verify_emmc_production.py',
                 'install_emmc_performance.py','qualify_storage_reboot.py'):
        paths.add(Path('/home/debian')/name)
for name in ('tzx_wifi_runtime.ko', 'tzx-wifi-runtime', 'tzx-wifi-runtime-test.sh'):
    paths.add(Path('/usr/local/lib/tzx-peripherals-accel1')/name)
for directory in ('/root/tzx-recovery/wifi-performance', '/root/tzx-recovery/cpu-performance-reference',
                  '/root/tzx-recovery/gpu-performance-policy', '/home/debian/gpu-performance',
                  '/home/debian/cpu-performance', '/home/debian/wifi-performance',
                  '/home/debian/performance-installed'):
    for p in Path(directory).rglob('*'):
        if p.is_file() and p.suffix not in ('.bin',) and '__pycache__' not in p.parts:
            paths.add(p)
for name in ('tzx-cpu-performance.service', 'tzx-gpu-performance.service',
             'tzx-cpufreq.service', 'tzx-cpu-cooling.service'):
    paths.add(Path('/etc/systemd/system')/name)
for name in ('cpu-performance-installed.json', 'gpu-performance-installed.json',
             'cpu-performance-qualified.json', 'gpu-performance-qualified.json',
             'wifi-performance-installed.json', 'performance-installed-validation.json',
             'performance-idle-validation.json',
             'screen-boot-health.json', 'screen-installed.json', 'dram-gpu-boot-health.json'):
    paths.add(Path('/var/lib/tzx')/name)
for name in ('install_cpu_performance.py', 'install_gpu_performance.py', 'install_wifi_performance.py',
             'upgrade_gpu_performance_policy.py', 'upgrade_cpu_performance_reference.py',
             'fix_cpu_performance_stop.py', 'verify_performance_installed.py', 'finalize_performance.py',
             'verify_gpu_performance_controls.py', 'verify_wifi_performance.py'):
    p = Path('/home/debian')/name
    if p.is_file():
        paths.add(p)
content = {}
for p in sorted(paths):
    assert p.is_file() and not p.is_symlink(), str(p)
    assert not any(word in str(p).lower() for word in ('private', 'credential', '.ssh', 'password'))
    data = p.read_bytes()
    assert len(data) < 2*1024*1024, (str(p), len(data))
    content[str(p).lstrip('/')] = data
snapshots = {}
for kind in (('cpu', 'gpu', 'emmc') if args.storage else ('cpu', 'gpu')):
    source = Path('/run/tzx-'+kind+'-performance.json')
    snapshots['runtime-'+kind+'.json'] = source.read_bytes()
snapshots['systemd-validation.log'] = subprocess.check_output(['journalctl', '-u',
    'tzx-emmc-production-reboot.service' if args.storage else 'tzx-performance-installed-validation3.service', '--no-pager'])
snapshots['thermal-and-clocks.txt'] = subprocess.check_output(['sh', '-c',
    'cat /sys/devices/system/cpu/cpufreq/policy*/scaling_cur_freq; '
    'cat /sys/kernel/debug/clk/gpu/clk_rate; cat /sys/kernel/debug/mmc0/ios /sys/kernel/debug/mmc1/ios; '
    'cat /sys/class/thermal/thermal_zone*/temp'])
content.update({'evidence/'+name: value for name,value in snapshots.items()})
manifest = {'cid': CID, 'boot_id': BOOT, 'profile': 'storage-performance-20261113' if args.storage else 'online-performance-20261113',
            'physical_reboot_tested': args.storage, 'normal_reboot_verified': args.storage,
            'poweroff_key_on_verified': False, 'screen_session_preserved': not args.storage,
            'boot_areas_changed': False, 'rootfs_backup': False,
            'files': {name: hashlib.sha256(data).hexdigest() for name,data in content.items()},
            'paired_screen_baseline': {'file': 'screen-poweron-installed-scoped-checkpoint.tar.gz',
                'sha256': '618213cdbc7b0f22988b0b705f111a0d4a1887bfc3452c1ee2afa10ea28a3bc8'},
            'limitations': ['CPU higher OPP voltage/rail mapping not yet qualified',
                '48MHz SDIO rejected due to firmware transfer errors; 24MHz requested/22.222222MHz actual',
                'native GPU devfreq OPP not enabled; leased fixed-parent performance with normal runtime gating',
                'current performance poweroff/key-on has not been tested' if args.storage else 'new performance profiles have not yet crossed a physical reboot',
                'VPU, HS200/400, zram and full SoC suspend remain unimplemented']}
target = Path('/home/debian/performance-storage-installed-checkpoint.tar.gz' if args.storage else '/home/debian/performance-installed-checkpoint.tar.gz')
assert not target.exists()
with tarfile.open(target, 'w:gz') as archive:
    for name,data in dict(content, **{'MANIFEST.json': (json.dumps(manifest, indent=2)+'\n').encode()}).items():
        info = tarfile.TarInfo(name)
        info.size = len(data)
        info.mode = 0o600
        archive.addfile(info, io.BytesIO(data))
target.chmod(0o644)
print('PERFORMANCE_INSTALLED_CHECKPOINT_CREATED', json.dumps({'path': str(target),
      'bytes': target.stat().st_size, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
      'files': len(content)}), flush=True)
