"""Qualify the installed divider service after a real boot and file audit."""
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import time

assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert not Path('/sys/module/panfrost').exists()
assert not Path('/var/lib/tzx/gpu-qualified').exists()
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
state_path = Path('/var/lib/tzx/cpufreq-runtime-installed.json')
state = json.loads(state_path.read_text())
assert state['boot_id'] != boot, 'Must verify a new boot, not the installer session'
for name, digest in state['files'].items():
    assert hashlib.sha256((Path('/') / name).read_bytes()).hexdigest() == digest
assert subprocess.check_output(['systemctl', 'is-enabled', 'tzx-cpufreq.service'], text=True).strip() == 'enabled'
for unit in ('lightdm', 'tzx-display', 'tzx-touch', 'tzx-audio', 'tzx-wifi', 'tzx-bluetooth',
             'tzx-cpub', 'tzx-cpufreq', 'tzx-battery', 'tzx-tablet-keys'):
    assert subprocess.check_output(['systemctl', 'is-active', unit], text=True).strip() == 'active', unit
assert not subprocess.check_output(['systemctl', '--failed', '--no-legend'], text=True).strip()
log = subprocess.check_output(['journalctl', '-k', '-b', '--no-pager'], text=True)
problems = [line for line in log.splitlines() if any(word in line for word in
            ('WARNING:', 'BUG:', 'Oops:', 'Call trace:', 'refcount_t:', 'cannot create duplicate filename'))]
assert not problems, problems
meminfo = Path('/proc/meminfo').read_text()
total = int(next(row.split()[1] for row in meminfo.splitlines() if row.startswith('MemTotal:')))
assert total >= 4000000
policies = [Path('/sys/devices/system/cpu/cpufreq') / f'policy{cpu}' for cpu in (0, 4)]
for policy in policies:
    assert (policy / 'scaling_governor').read_text().strip() == 'schedutil'
    assert (policy / 'scaling_driver').read_text().strip() == 'tzx-a523-divider'
    assert (policy / 'scaling_min_freq').read_text().strip() == '120000'
    assert (policy / 'scaling_max_freq').read_text().strip() == '480000'
    assert int((policy / 'cpuinfo_cur_freq').read_text()) in (120000, 240000, 480000)
ios = Path('/sys/kernel/debug/mmc1/ios').read_text()
assert '(4 bits)' in ios and '12000000 Hz' in ios, ios
framework_path = Path('/var/lib/tzx/cpufreq-framework-installed.json')
framework = json.loads(framework_path.read_text())
for name, digest in framework['mirror_sha256'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest
with open('/dev/mmcblk0', 'rb', buffering=0) as disk:
    bundle = os.pread(disk.fileno(), 14876672, 65536 * 512)
    header = os.pread(disk.fileno(), 512, 4096 * 512)
    loader = os.pread(disk.fileno(), 40960, 256 * 512)
assert hashlib.sha256(bundle).hexdigest() == framework['new_bundle_sha256']
assert header == bundle[:512]
assert hashlib.sha256(loader).hexdigest() == 'ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df'
audit = subprocess.run(['python3', '/home/debian/verify_safe_memory.py', '--files-only'],
                       capture_output=True, text=True, timeout=120)
print(audit.stdout, end='', flush=True)
assert audit.returncode == 0 and 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS' in audit.stdout, audit.stderr
state.update(state='manual_schedutil_service_stop_start_and_autostart_boot_verified',
             verified_boot_id=boot, verified_time_unix=int(time.time()),
             kernel_build=5, files_integrity='PASS', memory_total_kib=total,
             failed_services=0, gpu_enabled=False)
state_path.write_text(json.dumps(state, indent=2) + '\n')
framework.update(cpufreq_driver_autostart=True, cpufreq_driver_loaded=True,
                 verified_autostart_boot_id=boot)
framework_path.write_text(json.dumps(framework, indent=2) + '\n')
os.sync()
print('CPUFREQ_AUTOSTART_BOOT_FULL_RAM_WLAN_AND_FILE_INTEGRITY_PASS', json.dumps(state), flush=True)
