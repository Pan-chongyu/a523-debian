"""Own the production thermal zone; rely exclusively on existing divider QoS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument('operation', choices=('start', 'stop', 'verify'))
a = p.parse_args()
assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == Path('/etc/tzx/device-cid').read_text().strip()
assert int(Path('/proc/sys/kernel/tainted').read_text()) in (0, 4096)
ROOT = Path('/usr/local/lib/tzx-cpu-cooling')
MODULE = ROOT/'tzx_cpu_cooling.ko'
assert hashlib.sha256(MODULE.read_bytes()).hexdigest() == 'd37b67d234a699a45eaf0c7f9c350123271754091a77c498a6f99e883ac37efa'
policies = [Path('/sys/devices/system/cpu/cpufreq')/f'policy{cpu}' for cpu in (0, 4)]


def inspect():
    for policy in policies:
        assert (policy/'scaling_driver').read_text().strip() == 'tzx-a523-divider'
        assert (policy/'scaling_governor').read_text().strip() == 'schedutil'
    zones = {p.joinpath('type').read_text().strip(): p for p in Path('/sys/class/thermal').glob('thermal_zone*')}
    assert set(zones) == {'cpu-big-thermal', 'cpu-little-thermal', 'gpu-thermal', 'npu-thermal', 'ddr-thermal', 'tzx-board-thermal'}
    temperatures = {name: int((p/'temp').read_text()) for name, p in zones.items()}
    # A hot reading requires cooling; it is not a reason to reject the zone.
    assert all(0 < value <= 125000 for value in temperatures.values())
    zone = zones['tzx-board-thermal']
    assert (zone/'policy').read_text().strip() == 'step_wise'
    assert [(zone/f'trip_point_{i}_temp').read_text().strip() for i in range(3)] == ['70000', '80000', '95000']
    assert len(list(zone.glob('cdev*trip_point'))) == 4
    for name, value in (('first_trip', '70000'), ('second_trip', '80000')):
        assert (Path('/sys/module/tzx_cpu_cooling/parameters')/name).read_text().strip() == value
    devices = {p.joinpath('type').read_text().strip(): p for p in Path('/sys/class/thermal').glob('cooling_device*')}
    owned = {'tzx-cpu-cluster0', 'tzx-cpu-cluster1'}
    assert owned <= set(devices)
    states = {name: int((devices[name]/'cur_state').read_text()) for name in owned}
    assert all(0 <= state <= 2 for state in states.values())
    return {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'temperatures_mC': temperatures, 'cooling_states': states,
            'cpu_maximum_kHz': [int((p/'scaling_max_freq').read_text()) for p in policies],
            'trips_mC': [70000, 80000, 95000], 'governor': 'step_wise'}


if a.operation == 'stop':
    if Path('/sys/module/tzx_cpu_cooling').exists():
        subprocess.run(['rmmod', 'tzx_cpu_cooling'], check=True, timeout=20)
    assert not any((p/'type').read_text().strip() in {'tzx-cpu-cluster0', 'tzx-cpu-cluster1'}
                   for p in Path('/sys/class/thermal').glob('cooling_device*'))
    print('TZX_CPU_COOLING_REMOVED_FREQUENCY_QOS_RELEASED', flush=True)
else:
    subprocess.run(['python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard'], check=True, timeout=30)
    if a.operation == 'start':
        assert not Path('/sys/module/tzx_cpu_cooling').exists()
        subprocess.run(['insmod', str(MODULE)], check=True, timeout=20)
        time.sleep(2)
    print('TZX_CPU_COOLING_PRODUCTION_ZONE_AND_QOS_PASS', json.dumps(inspect()), flush=True)
