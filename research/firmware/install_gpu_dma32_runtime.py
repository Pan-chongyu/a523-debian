"""Install the candidate only after the named manual trials and file audit pass."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--enable-for-reboot', action='store_true')
args = parser.parse_args()
assert os.geteuid() == 0 and os.uname().release == '7.3.3-tzx-a523-accel1'
assert '#4 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert not Path('/sys/module/panfrost').exists(), 'Finish the manual trial cleanup first'
assert not Path('/var/lib/tzx/gpu-qualified').exists()
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
proof = {}
for unit, success in (
    ('tzx-gpu-dma32-desktop-final.service',
     'GPU_DMA32_MMU_DESKTOP_AND_NATIVE_PRESENT_QUALIFICATION_PASS'),
    ('tzx-gpu-dma32-post-desktop-audit.service', 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS')):
    properties = subprocess.check_output(['systemctl', 'show', unit, '-p', 'Result',
                                         '-p', 'ActiveState', '-p', 'ExecMainStatus'], text=True)
    assert 'Result=success\n' in properties and 'ExecMainStatus=0\n' in properties
    assert 'ActiveState=inactive\n' in properties, (unit, properties)
    journal = subprocess.check_output(['journalctl', '-b', '0', '-u', unit, '--no-pager'], text=True)
    assert success in journal, unit
    proof[unit] = hashlib.sha256(journal.encode()).hexdigest()
fd = os.open('/dev/mmcblk0', os.O_RDONLY)
try:
    bundle = os.pread(fd, 14809088, 4096 * 512)
finally:
    os.close(fd)
assert hashlib.sha256(bundle).hexdigest() == '32648d80d699892b3dcfe0be37fdc07a5ed30d95d8b9ad8cf2140bb6f3181799'
stage = Path(__file__).resolve().parent
files = json.loads((stage / 'FILES.json').read_text())
for name, digest in files.items():
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    assert name.startswith(('lib/modules/7.3.3-tzx-a523-accel1/updates/tzx-dma32/',
                            'usr/local/lib/tzx-gpu-dma32/', 'etc/modprobe.d/tzx-gpu-dma32.conf',
                            'etc/systemd/system/'))
    assert hashlib.sha256((stage / name).read_bytes()).hexdigest() == digest
backup = Path('/root/tzx-recovery/gpu-dma32')
backup.mkdir(parents=True, exist_ok=True)
assert not (backup / 'before.json').exists(), 'Existing recovery snapshot must be kept intact'
previous = {}
for name in files:
    target = Path('/') / name
    assert not target.is_symlink(), name
    if target.exists():
        saved = backup / 'files' / name
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(target.read_bytes())
        previous[name] = {'sha256': hashlib.sha256(saved.read_bytes()).hexdigest(),
                          'mode': target.stat().st_mode & 0o777}
    else:
        previous[name] = None
(backup / 'before.json').write_text(json.dumps(previous, indent=2) + '\n')
(backup / 'installed-files.json').write_text(json.dumps(files, indent=2) + '\n')
(backup / 'rollback.py').write_bytes((stage / 'rollback_gpu_dma32_runtime.py').read_bytes())
for name, digest in files.items():
    target = Path('/') / name
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.tzx-new')
    temporary.write_bytes((stage / name).read_bytes())
    temporary.chmod(0o644)
    temporary.replace(target)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
subprocess.run(['depmod', '-a', os.uname().release], check=True)
for module in ('panfrost', 'tzx_display'):
    actual = subprocess.check_output(['modinfo', '-n', module], text=True).strip()
    assert actual == '/lib/modules/' + os.uname().release + '/updates/tzx-dma32/' + module + '.ko'
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemd-analyze', '--man=no', 'verify', 'tzx-gpu.service',
                'tzx-display.service', 'lightdm.service', 'tzx-gpu-dma32-health.service',
                'tzx-gpu-dma32-fallback.service'], check=True)
if args.enable_for_reboot:
    marker = Path('/var/lib/tzx/gpu-qualified')
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({'state': 'manual_trials_passed_autostart_reboot_pending',
                     'time_unix': int(time.time()),
                     'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                     'proof_journal_sha256': proof, 'files': files}, indent=2) + '\n')
    subprocess.run(['systemctl', 'enable', 'tzx-gpu.service', 'tzx-gpu-dma32-health.service'], check=True)
os.sync()
print('GPU_DMA32_RUNTIME_INSTALLED_REBOOT_REQUIRED', json.dumps({
    'files': len(files), 'enable_for_reboot': args.enable_for_reboot,
    'running_desktop_changed': False, 'raw_boot_bundle_changed': False}), flush=True)
