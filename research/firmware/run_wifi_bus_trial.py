"""Run two reversible four-bit Wi-Fi initializations at the existing 12 MHz."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

assert os.geteuid() == 0 and '#4 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert not Path('/sys/module/panfrost').exists()
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
baseline = json.loads(Path('/home/debian/wifi-transfer-onebit-baseline.json').read_text())
assert baseline['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert len(baseline['transfers']) == 4 and all(row['sha256'] == 'PASS' for row in baseline['transfers'])
base = Path('/usr/local/lib/tzx-peripherals-accel1')
candidate = Path('/home/debian/tzx_wifi_runtime-fourbit.ko')
digest = '313e014683a700cf4157eb08f7136b6af12c938464d0e520690a2db72890f74b'
assert hashlib.sha256(candidate.read_bytes()).hexdigest() == digest
expected = {'tzx_wifi_runtime.ko': '301839a7b0d84bc7093ae13266fd36a593d7e3dd30799fe4db1b22eecbc34073',
            'tzx-wifi-runtime': '9f9da4016286d6e4e305d52ef4ab063269265372a29926514df473f17a0720e1',
            'tzx-wifi-runtime-test.sh': '3a4c7bbb5923c2e10c376cc2579c2754e20919435fa32a9c12934cf82c6f5c56',
            'aic8800_bsp.ko': '9bf1e8f5015861720077e870e583bf7a58395b6a596245d833e0d60e834f3440',
            'aic8800_fdrv.ko': '1bc81c0e382ddba06aa67e8fa9d754b7baa3746ce6529b34be3f795c9861db42'}
for name, checksum in expected.items():
    assert hashlib.sha256((base / name).read_bytes()).hexdigest() == checksum, name
stage = Path('/run/tzx-wifi-fourbit')
stage.mkdir(exist_ok=False)
for name in expected:
    shutil.copyfile(base / name, stage / name)
shutil.copyfile(candidate, stage / 'tzx_wifi_runtime.ko')
for name in ('tzx-wifi-runtime', 'tzx-wifi-runtime-test.sh'):
    text = (stage / name).read_text()
    text = text.replace(str(base), str(stage))
    if name.endswith('test.sh'):
        assert text.count(expected['tzx_wifi_runtime.ko']) == 1
        text = text.replace(expected['tzx_wifi_runtime.ko'], digest)
        old = '    insmod ' + str(stage / 'tzx_wifi_runtime.ko') + '\n'
        assert text.count(old) == 1
        text = text.replace(old, old.rstrip() + ' bus_width=4\n')
    (stage / name).write_text(text)
override = Path('/run/systemd/system/tzx-wifi.service.d/95-fourbit-test.conf')
assert not override.exists()
shutil.copyfile('/home/debian/cleanup_wifi_bus_trial.py', '/run/tzx-wifi-bus-rollback.py')


def run(*command, timeout=65):
    print('WIFI_TRIAL_COMMAND', json.dumps(command), flush=True)
    subprocess.run(command, check=True, timeout=timeout)


run('systemd-run', '--unit=tzx-wifi-bus-rollback-fourbit', '--on-active=8m',
    '/usr/bin/python3', '/run/tzx-wifi-bus-rollback.py')
try:
    for cycle in range(2):
        run('systemctl', 'stop', 'tzx-bluetooth.service')
        run('systemctl', 'stop', 'tzx-wifi.service')
        if not override.exists():
            override.parent.mkdir(parents=True, exist_ok=True)
            override.write_text('[Service]\nExecStart=\nExecStart=/bin/sh ' + str(stage / 'tzx-wifi-runtime')
                                + ' start\nExecStop=\nExecStop=/bin/sh '
                                + str(stage / 'tzx-wifi-runtime') + ' stop\n')
            run('systemctl', 'daemon-reload')
        run('systemctl', 'start', 'tzx-wifi.service')
        run('systemctl', 'start', 'tzx-bluetooth.service')
        for attempt in range(45):
            route = subprocess.check_output(['ip', 'route', 'get', '10.0.2.40'], text=True)
            if 'dev wlan0' in route:
                break
            time.sleep(1)
        else:
            raise RuntimeError('WLAN did not reconnect after four-bit initialization')
        ios = Path('/sys/kernel/debug/mmc1/ios').read_text()
        assert '12000000 Hz' in ios and '(4 bits)' in ios, ios
        assert int(Path('/sys/module/tzx_wifi_runtime/parameters/bus_width').read_text()) == 4
        print('WIFI_FOUR_BIT_IOS', json.dumps(ios), flush=True)
        run('python3', '/home/debian/verify_wifi_transfer.py', '--label', 'fourbit-' + str(cycle + 1),
            '--cycles', '2', timeout=150)
        errors = Path('/sys/kernel/debug/mmc1/err_stats').read_text()
        assert not any(int(value) for value in re.findall(r':\s*(\d+)', errors)), errors
        assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    print('WIFI_FOUR_BIT_TWO_LOADS_AND_VERIFIED_LOCAL_TRANSFER_PASS', flush=True)
finally:
    run('python3', '/run/tzx-wifi-bus-rollback.py', timeout=150)
