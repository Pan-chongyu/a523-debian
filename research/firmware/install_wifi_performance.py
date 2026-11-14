"""Promote only the twice-tested 24 MHz SDIO profile, retaining a full rollback."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

BASE = Path('/usr/local/lib/tzx-peripherals-accel1')
BACKUP = Path('/root/tzx-recovery/wifi-performance')
STATE = Path('/var/lib/tzx/wifi-performance-installed.json')
assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert len(sys.argv) == 2 and sys.argv[1] in ('install', 'restore')

def run(*command, timeout=85):
    return subprocess.check_output(command, stderr=subprocess.STDOUT, text=True, timeout=timeout)

def restart():
    run('systemctl', 'start', 'tzx-wifi.service')
    run('systemctl', 'start', 'tzx-bluetooth.service')
    for attempt in range(45):
        if 'dev wlan0' in run('ip', 'route', 'get', '10.0.2.40'):
            break
        time.sleep(1)

def restore():
    state = json.loads(STATE.read_text())
    run('systemctl', 'stop', 'tzx-bluetooth.service')
    run('systemctl', 'stop', 'tzx-wifi.service')
    for name, value in state['before'].items():
        source = BACKUP/Path(name).name
        assert hashlib.sha256(source.read_bytes()).hexdigest() == value['sha256']
        target = Path(name)
        target.write_bytes(source.read_bytes())
        target.chmod(value['mode'])
    restart()
    assert Path('/sys/kernel/debug/mmc1/clock').read_text().strip() == '12000000'
    state['state'] = 'restored-12MHz'
    STATE.write_text(json.dumps(state, indent=2)+'\n')
    print('WIFI_PERFORMANCE_12_MHZ_ORIGINAL_FILES_RESTORED', flush=True)

if sys.argv[1] == 'restore':
    restore()
    raise SystemExit(0)

assert not BACKUP.exists() and not STATE.exists()
assert not Path('/run/systemd/system/tzx-wifi.service.d/95-performance-test.conf').exists()
trial = json.loads(Path('/home/debian/wifi-performance/trial-result.json').read_text())
assert trial['status'] == 'PASS' and trial['baseline_restored']
assert trial['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert len(trial['reports']) == 3
assert all('24000000 Hz' in r['mmc_ios'] and len(r['transfers']) == 8 for r in trial['reports'][1:])
assert all(t['sha256'] == 'PASS' for r in trial['reports'] for t in r['transfers'])
old_sha = '313e014683a700cf4157eb08f7136b6af12c938464d0e520690a2db72890f74b'
new_sha = 'c89472e3d800beba1796940a7c6afc78d82d22166f7a72b4ae9310caf222c751'
assert trial['module_sha256'] == new_sha
module = Path('/home/debian/wifi-performance/tzx_wifi_runtime.ko').read_bytes()
assert hashlib.sha256(module).hexdigest() == new_sha
assert hashlib.sha256((BASE/'tzx_wifi_runtime.ko').read_bytes()).hexdigest() == old_sha
files = {BASE/'tzx_wifi_runtime.ko': module}
text = (BASE/'tzx-wifi-runtime-test.sh').read_text()
assert text.count(old_sha) == 1 and text.count('bus_width=4\n') == 1
text = text.replace(old_sha, new_sha).replace('bus_width=4\n', 'bus_width=4 max_frequency_mhz=24\n')
files[BASE/'tzx-wifi-runtime-test.sh'] = text.encode()
text = (BASE/'tzx-wifi-runtime').read_text()
assert text.count("'12000000'") == 1
text = text.replace("'12000000'", "'24000000'")
files[BASE/'tzx-wifi-runtime'] = text.encode()
for name, data in files.items():
    if name.name != 'tzx_wifi_runtime.ko':
        subprocess.run(['/bin/sh', '-n'], input=data, check=True)
BACKUP.mkdir(exist_ok=False)
before = {}
for name in files:
    assert not name.is_symlink()
    (BACKUP/name.name).write_bytes(name.read_bytes())
    before[str(name)] = {'sha256': hashlib.sha256(name.read_bytes()).hexdigest(), 'mode': name.stat().st_mode & 0o777}
state = {'state': 'installing', 'before': before, 'files': {str(p): hashlib.sha256(d).hexdigest() for p,d in files.items()},
         'trial': trial, 'requested_clock_hz': 24000000, 'actual_clock_hz': 22222222,
         'rejected_rate_hz': 48000000, 'reason': 'firmware SDIO transfer error at 48MHz',
         'boot_areas_changed': False, 'cold_boot_tested': False}
STATE.write_text(json.dumps(state, indent=2)+'\n')
try:
    run('systemctl', 'stop', 'tzx-bluetooth.service')
    run('systemctl', 'stop', 'tzx-wifi.service')
    for name, data in files.items():
        temporary = name.with_name(name.name+'.performance-new')
        temporary.write_bytes(data)
        temporary.chmod(before[str(name)]['mode'])
        temporary.replace(name)
    restart()
    assert Path('/sys/kernel/debug/mmc1/clock').read_text().strip() == '24000000'
    assert 'actual clock:\t22222222 Hz' in Path('/sys/kernel/debug/mmc1/ios').read_text()
    run('systemctl', 'is-active', 'tzx-wifi.service', 'tzx-bluetooth.service')
    state['state'] = 'installed-online-two-loads-verified'
    STATE.write_text(json.dumps(state, indent=2)+'\n')
    print('WIFI_PERFORMANCE_24_MHZ_REQUEST_22_22_MHZ_ACTUAL_INSTALLED', flush=True)
except BaseException:
    restore()
    raise
