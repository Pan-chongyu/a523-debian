"""Remove only the temporary Wi-Fi performance override and restore 12 MHz."""
import json
from pathlib import Path
import subprocess

override = Path('/run/systemd/system/tzx-wifi.service.d/95-performance-test.conf')
def run(*args):
    subprocess.run(args, check=True, timeout=80, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
if override.exists():
    run('systemctl', 'stop', 'tzx-bluetooth.service')
    run('systemctl', 'stop', 'tzx-wifi.service')
    override.unlink()
    run('systemctl', 'daemon-reload')
    run('systemctl', 'start', 'tzx-wifi.service')
    run('systemctl', 'start', 'tzx-bluetooth.service')
subprocess.run(['ip', 'neigh', 'del', '10.0.2.40', 'dev', 'wlan0'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
assert Path('/sys/kernel/debug/mmc1/clock').read_text().strip() == '12000000'
assert not Path('/sys/module/tzx_wifi_runtime/parameters/max_frequency_mhz').exists()
print('WIFI_PERFORMANCE_ORIGINAL_12_MHZ_RESTORED', flush=True)
