"""Compare 12/24/48 MHz with identical, byte-checked WLAN transfers."""
import argparse
import array
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time

ROOT = Path('/home/debian/wifi-performance')
parser = argparse.ArgumentParser()
parser.add_argument('--rates', type=int, nargs='+', choices=(24, 48), default=[24, 48, 48])
args = parser.parse_args()
assert 1 <= len(args.rates) <= 3
BASE = Path('/usr/local/lib/tzx-peripherals-accel1')
STAGE = Path('/run/tzx-wifi-performance-'+str(os.getpid()))
OVERRIDE = Path('/run/systemd/system/tzx-wifi.service.d/95-performance-test.conf')
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
OLD_SHA = '313e014683a700cf4157eb08f7136b6af12c938464d0e520690a2db72890f74b'
NEW_SHA = 'c89472e3d800beba1796940a7c6afc78d82d22166f7a72b4ae9310caf222c751'
assert hashlib.sha256((ROOT/'tzx_wifi_runtime.ko').read_bytes()).hexdigest() == NEW_SHA
assert hashlib.sha256((BASE/'tzx_wifi_runtime.ko').read_bytes()).hexdigest() == OLD_SHA
assert not OVERRIDE.exists() and not STAGE.exists()
STAGE.mkdir()
for name in ('tzx-wifi-runtime', 'tzx-wifi-runtime-test.sh', 'aic8800_bsp.ko', 'aic8800_fdrv.ko'):
    shutil.copyfile(BASE/name, STAGE/name)
shutil.copyfile(ROOT/'tzx_wifi_runtime.ko', STAGE/'tzx_wifi_runtime.ko')
watchdog = None
ping_thread = None
stop_ping = threading.Event()
started = time.monotonic()
reports = []

def run(*command, timeout=100):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    with (ROOT/'commands.log').open('a') as log:
        log.write(repr(command)+'\n'+result.stdout+'\n')
    assert result.returncode == 0, (command, result.returncode, result.stdout[-1500:])
    return result.stdout

def state(stage, **extra):
    value = {'stage': stage, 'boot_id': BOOT, 'elapsed': round(time.monotonic()-started, 2), **extra}
    (ROOT/'trial-state.json').write_text(json.dumps(value, indent=2)+'\n')
    print(stage, json.dumps(extra), flush=True)

def neighbor():
    # Host VPN prevents normal ARP replies. This temporary fixture avoids
    # changing host routes or firewall; every tablet data packet uses WLAN.
    run('ip', 'neigh', 'replace', '10.0.2.40', 'lladdr', '50:84:92:7b:aa:7a',
        'nud', 'permanent', 'dev', 'wlan0')

def transfer(label, cycles):
    neighbor()
    run('python3', '/home/debian/verify_wifi_transfer.py', '--label', label,
        '--cycles', str(cycles), timeout=180)
    report = json.loads(Path('/home/debian/wifi-transfer-'+label+'.json').read_text())
    assert report['boot_id'] == BOOT
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    for service in ('tzx-cpu-performance.service', 'tzx-gpu-performance.service', 'lightdm.service'):
        run('systemctl', 'is-active', service)
    reports.append(report)
    print('TRANSFER_PASS', json.dumps({'label': label, 'transfers': report['transfers'],
                                     'ios': report['mmc_ios']}), flush=True)

def load_rate(rate):
    run('systemctl', 'stop', 'tzx-bluetooth.service')
    run('systemctl', 'stop', 'tzx-wifi.service')
    text = (BASE/'tzx-wifi-runtime-test.sh').read_text().replace(str(BASE), str(STAGE))
    assert text.count(OLD_SHA) == 1 and text.count('bus_width=4\n') == 1
    text = text.replace(OLD_SHA, NEW_SHA).replace('bus_width=4\n', 'bus_width=4 max_frequency_mhz='+str(rate)+'\n')
    (STAGE/'tzx-wifi-runtime-test.sh').write_text(text)
    text = (BASE/'tzx-wifi-runtime').read_text().replace(str(BASE), str(STAGE))
    assert text.count("'12000000'") == 1
    text = text.replace("'12000000'", repr(str(rate*1000000)))
    (STAGE/'tzx-wifi-runtime').write_text(text)
    run('/bin/sh', '-n', str(STAGE/'tzx-wifi-runtime'))
    run('/bin/sh', '-n', str(STAGE/'tzx-wifi-runtime-test.sh'))
    OVERRIDE.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDE.write_text('[Service]\nExecStart=\nExecStart=/bin/sh '+str(STAGE/'tzx-wifi-runtime')+
                        ' start\nExecStop=\nExecStop=/bin/sh '+str(STAGE/'tzx-wifi-runtime')+' stop\n')
    run('systemctl', 'daemon-reload')
    run('systemctl', 'start', 'tzx-wifi.service')
    run('systemctl', 'start', 'tzx-bluetooth.service')
    for attempt in range(45):
        route = run('ip', 'route', 'get', '10.0.2.40')
        if 'dev wlan0' in route and 'src 10.0.2.139' in route:
            break
        time.sleep(1)
    else:
        raise RuntimeError('WLAN did not reconnect')
    assert Path('/sys/kernel/debug/mmc1/clock').read_text().strip() == str(rate*1000000)
    assert int(Path('/sys/module/tzx_wifi_runtime/parameters/max_frequency_mhz').read_text()) == rate
    assert '(4 bits)' in Path('/sys/kernel/debug/mmc1/ios').read_text()

def ping():
    while not stop_ping.wait(2):
        if time.monotonic()-started > 540:
            break
        os.write(watchdog, b'.')

def interrupt(signum, frame):
    raise RuntimeError('Interrupted '+str(signum))

signal.signal(signal.SIGTERM, interrupt)
signal.signal(signal.SIGINT, interrupt)
passed = False
try:
    watchdog = os.open('/dev/watchdog', os.O_WRONLY | os.O_CLOEXEC)
    value = array.array('i', [16])
    fcntl.ioctl(watchdog, 0xc0045706, value, True)
    assert value[0] >= 10
    ping_thread = threading.Thread(target=ping, daemon=True)
    ping_thread.start()
    rollback = 'tzx-wifi-performance-rollback-'+str(os.getpid())
    run('systemd-run', '--unit='+rollback, '--on-active=8min',
        '/usr/bin/python3', '/home/debian/cleanup_wifi_performance.py')
    state('BASELINE_12_MHZ')
    transfer('performance-baseline12', 2)
    for number, rate in enumerate(args.rates, 1):
        state('SDIO_RATE_TRIAL', mhz=rate, number=number)
        load_rate(rate)
        transfer('performance-%d-%dMHz' % (number, rate), 4)
    passed = True
finally:
    run('python3', '/home/debian/cleanup_wifi_performance.py', timeout=180)
    run('systemctl', 'stop', rollback+'.timer')
    stop_ping.set()
    if ping_thread:
        ping_thread.join(timeout=5)
    if watchdog is not None:
        os.write(watchdog, b'V')
        os.close(watchdog)
if passed:
    result = {'status': 'PASS', 'boot_id': BOOT, 'reports': reports, 'baseline_restored': True,
              'temporary_static_neighbor_for_host_VPN': True, 'host_network_configuration_changed': False,
              'elapsed': round(time.monotonic()-started, 2), 'module_sha256': NEW_SHA}
    (ROOT/'trial-result.json').write_text(json.dumps(result, indent=2)+'\n')
    state('WIFI_PERFORMANCE_TRIAL_PASS', elapsed=result['elapsed'])
