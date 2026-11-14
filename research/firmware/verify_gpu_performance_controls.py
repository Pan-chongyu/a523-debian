"""Exercise real-temperature caps, lease expiry and invalid-rate rejection."""
import json
from pathlib import Path
import subprocess
import time

ROOT = Path('/home/debian/gpu-performance')
PARAM = Path('/sys/module/tzx_gpu_performance/parameters')
records = []

def load(*parameters):
    subprocess.run(['insmod', str(ROOT / 'tzx_gpu_performance.ko'), *parameters], check=True)

def unload():
    if PARAM.exists():
        subprocess.run(['rmmod', 'tzx_gpu_performance'], check=True, timeout=10)

def actual():
    assert int((PARAM / 'fault').read_text()) == 0
    return int((PARAM / 'actual_mhz').read_text())

assert json.loads((ROOT / 'trial-result.json').read_text())['status'] == 'PASS'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
try:
    unload()
    load('active_only=0', 'lease_seconds=5', 'first_trip=30000')
    assert int((PARAM / 'temperature_mc').read_text()) > 30000
    (PARAM / 'requested_mhz').write_text('600')
    assert actual() == 400
    records.append({'check': 'first thermal cap', 'request_mhz': 600, 'actual_mhz': actual()})
    try:
        (PARAM / 'requested_mhz').write_text('800')
        raise AssertionError('Unqualified 800 MHz accepted')
    except OSError:
        pass
    assert actual() == 400
    time.sleep(6)
    assert actual() == 200
    records.append({'check': 'lease expired after 5 seconds', 'actual_mhz': actual()})
    unload()
    load('active_only=0', 'first_trip=30000', 'second_trip=35000')
    assert int((PARAM / 'temperature_mc').read_text()) > 35000
    (PARAM / 'requested_mhz').write_text('600')
    assert actual() == 200
    records.append({'check': 'second thermal cap', 'request_mhz': 600, 'actual_mhz': actual()})
    unload()
    load()
    (PARAM / 'requested_mhz').write_text('600')
    time.sleep(2)
    status = Path('/sys/bus/platform/devices/1800000.gpu/power/runtime_status').read_text().strip()
    if status == 'suspended':
        assert actual() == 200
    assert Path('/sys/bus/platform/devices/1800000.gpu/power/control').read_text().strip() == 'auto'
    records.append({'check': 'runtime autosuspend preserved', 'status': status, 'actual_mhz': actual()})
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    result = {'status': 'PASS', 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'records': records, 'invalid_800_mhz_rejected': True, 'temperature_emulated': False}
    (ROOT / 'controls-result.json').write_text(json.dumps(result, indent=2)+'\n')
    print('GPU_PERFORMANCE_CONTROLS_PASS', json.dumps(result), flush=True)
finally:
    unload()
