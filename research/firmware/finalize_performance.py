"""Record final actual-file identity and normal idle behavior, without restart."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

assert os.geteuid() == 0
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
STATE = Path('/var/lib/tzx')
proof = json.loads((STATE/'performance-installed-validation.json').read_text())
assert proof['status'] == 'PASS' and proof['boot_id'] == BOOT
assert proof['actual_cpu_maximum_khz'] == [792000, 1008000]
assert proof['actual_gpu_maximum_hz'] == 600000000
assert subprocess.check_output(['pgrep', '-x', 'Xorg'], text=True).strip() == proof['xorg_pid_unchanged']
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
units = ['tzx-cpu-performance.service', 'tzx-gpu-performance.service',
         'tzx-wifi.service', 'tzx-bluetooth.service']
subprocess.run(['systemctl', 'is-active', *units], check=True)
subprocess.run(['systemctl', 'is-enabled', *units], check=True)
subprocess.run(['systemd-analyze', 'verify', '/etc/systemd/system/tzx-cpu-performance.service',
                '/etc/systemd/system/tzx-gpu-performance.service'], check=True)
actual_manifests = {}
for kind in ('cpu', 'gpu'):
    manifest = json.loads((Path('/usr/local/lib/tzx-'+kind+'-performance')/'manifest.json').read_text())
    installed = json.loads((STATE/(kind+'-performance-installed.json')).read_text())
    assert installed['manifest'] == manifest
    for name, digest in manifest['files'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    actual_manifests[kind] = manifest
wifi = json.loads((STATE/'wifi-performance-installed.json').read_text())
for name, digest in wifi['files'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
assert 'actual clock:\t22222222 Hz' in Path('/sys/kernel/debug/mmc1/ios').read_text()
assert 'PERMANENT' not in subprocess.check_output(['ip', 'neigh', 'show', 'dev', 'wlan0'], text=True)

samples = []
for unused in range(30):
    samples.append({
        'cpu_khz': [int(Path('/sys/devices/system/cpu/cpufreq/policy'+str(n)+'/scaling_cur_freq').read_text()) for n in (0,4)],
        'gpu_runtime': Path('/sys/bus/platform/devices/1800000.gpu/power/runtime_status').read_text().strip(),
        'gpu_selected_hz': int(Path('/sys/kernel/debug/clk/gpu/clk_rate').read_text())})
    time.sleep(0.4)
minimum = [min(s['cpu_khz'][n] for s in samples) for n in (0,1)]
assert minimum == [120000, 120000], minimum
assert any(s['gpu_runtime'] == 'suspended' for s in samples)
assert Path('/sys/bus/platform/devices/1800000.gpu/power/control').read_text().strip() == 'auto'
assert not subprocess.check_output(['systemctl', '--failed', '--no-legend', '--plain'], text=True).strip()
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
idle = {'status': 'PASS', 'boot_id': BOOT, 'minimum_cpu_khz': minimum,
        'gpu_runtime_suspend_observed': True, 'samples': samples,
        'actual_installed_manifests': actual_manifests, 'wifi_files': wifi['files'],
        'physical_reboot_tested': False, 'screen_session_restarted': False}
(STATE/'performance-idle-validation.json').write_text(json.dumps(idle, indent=2)+'\n')
for kind, manifest in actual_manifests.items():
    for suffix in ('installed', 'qualified'):
        p = STATE/(kind+'-performance-'+suffix+'.json')
        record = json.loads(p.read_text())
        record['production_validation'] = {
            'boot_id': BOOT, 'status': 'PASS', 'manifest': manifest,
            'record': '/var/lib/tzx/performance-installed-validation.json',
            'sha256': hashlib.sha256((STATE/'performance-installed-validation.json').read_bytes()).hexdigest(),
            'idle_record': '/var/lib/tzx/performance-idle-validation.json',
            'physical_reboot_tested': False}
        temporary = p.with_suffix('.json.finalizing')
        temporary.write_text(json.dumps(record, indent=2)+'\n')
        temporary.replace(p)
subprocess.run(['sync'], check=True)
print('PERFORMANCE_FINAL_ACTUAL_FILES_AND_IDLE_PASS', json.dumps({
    'boot_id': BOOT, 'idle_minimum_khz': minimum, 'gpu_runtime_suspend_observed': True,
    'physical_reboot_tested': False, 'xorg_pid': proof['xorg_pid_unchanged']}))
