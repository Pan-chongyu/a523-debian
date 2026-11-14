"""Restore the installed one-bit WLAN service after a temporary host trial."""
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
override = Path('/run/systemd/system/tzx-wifi.service.d/95-fourbit-test.conf')
if override.exists():
    subprocess.run(['systemctl', 'stop', 'tzx-bluetooth.service'], check=True, timeout=25)
    subprocess.run(['systemctl', 'stop', 'tzx-wifi.service'], check=True, timeout=45)
    override.unlink()
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'start', 'tzx-wifi.service'], check=True, timeout=65)
    subprocess.run(['systemctl', 'start', 'tzx-bluetooth.service'], check=True, timeout=50)
timers = subprocess.check_output(['systemctl', 'list-units', '--all', '--type=timer',
                                  '--plain', '--no-legend'], text=True)
for row in timers.splitlines():
    name = row.split()[0]
    if name.startswith('tzx-wifi-bus-rollback-') and name.endswith('.timer'):
        subprocess.run(['systemctl', 'stop', name], check=True)
ios = Path('/sys/kernel/debug/mmc1/ios').read_text()
assert '12000000 Hz' in ios and '(1 bits)' in ios, ios
assert not Path('/proc/device-tree/soc/mmc@4021000/bus-width').exists()
report = {'baseline_one_bit_restored': True, 'desktop_restarted': False,
          'mmc_ios': ios, 'bluetooth_service': subprocess.check_output(
              ['systemctl', 'is-active', 'tzx-bluetooth.service'], text=True).strip()}
Path('/run/tzx-wifi-bus-cleanup.json').write_text(json.dumps(report, indent=2) + '\n')
print('WIFI_BUS_BASELINE_RESTORED', json.dumps(report), flush=True)
