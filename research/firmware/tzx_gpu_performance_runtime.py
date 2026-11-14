"""Qualified GPU performance as an additive, fail-closed service."""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading

ROOT = Path('/usr/local/lib/tzx-gpu-performance')
PARAM = Path('/sys/module/tzx_gpu_performance/parameters')
QUALIFIED = Path('/var/lib/tzx/gpu-performance-qualified.json')
PENDING = Path('/var/lib/tzx/gpu-performance-pending.json')
STATUS = Path('/run/tzx-gpu-performance.json')
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
quit_event = threading.Event()
owned = False

def atomic(path, value):
    temporary = path.with_suffix(path.suffix+'.new')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)

def faults():
    return [s for s in subprocess.check_output(['dmesg'], text=True).splitlines()
            if re.search(r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b', s, re.I)]

def stop(signum, frame):
    quit_event.set()

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
assert os.geteuid() == 0
try:
    manifest = json.loads((ROOT/'manifest.json').read_text())
    for name, digest in manifest['files'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    qualification = json.loads(QUALIFIED.read_text())
    assert qualification['profile'] == 'fixed-parent-900mV-200-600MHz'
    assert qualification['trial']['status'] == qualification['controls']['status'] == 'PASS'
    if PENDING.exists():
        previous = json.loads(PENDING.read_text())
        assert previous['boot_id'] == BOOT, 'Unclean previous performance boot; keep baseline 200 MHz'
    subprocess.run(['python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard'], check=True, timeout=30)
    health = json.loads(Path('/var/lib/tzx/dram-gpu-boot-health.json').read_text())
    assert health['boot_id'] == BOOT and health['status'] == 'PASS'
    assert not PARAM.exists(), 'Another clock controller owns this session'
    assert not faults()
    assert Path('/sys/bus/platform/devices/1800000.gpu/power/control').read_text().strip() == 'auto'
    atomic(PENDING, {'boot_id': BOOT, 'profile': qualification['profile'], 'state': 'running'})
    # Keep the selected clock across autosuspend. The GPU still gates its
    # clocks normally; brief jobs can then resume immediately at 600 MHz
    # instead of waiting for the 200 ms thermal worker to notice them.
    subprocess.run(['insmod', str(ROOT/'tzx_gpu_performance.ko'), 'active_only=0'], check=True, timeout=15)
    owned = True
    for name, value in (('first_trip', '65000'), ('second_trip', '70000'),
                        ('active_only', 'N'), ('lease_seconds', '30')):
        assert (PARAM/name).read_text().strip() == value, name
    while not quit_event.is_set():
        assert Path('/var/lib/tzx/gpu-qualified').exists()
        assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
        assert not faults()
        assert int((PARAM/'fault').read_text()) == 0
        (PARAM/'requested_mhz').write_text('600')
        state = {'boot_id': BOOT, 'maximum_mhz': 600,
                 'actual_mhz': int((PARAM/'actual_mhz').read_text()),
                 'maximum_temperature_mc': int((PARAM/'temperature_mc').read_text()),
                 'runtime_status': Path('/sys/bus/platform/devices/1800000.gpu/power/runtime_status').read_text().strip(),
                 'thermal_caps_mc': [65000, 70000], 'lease_seconds': 30,
                 'voltage_changed': False, 'PLL_changed': False, 'state': 'active'}
        atomic(STATUS, state)
        quit_event.wait(5)
except BaseException as error:
    atomic(Path('/var/lib/tzx/gpu-performance-failure.json'), {'boot_id': BOOT, 'error': repr(error)})
    if QUALIFIED.exists():
        QUALIFIED.replace('/var/lib/tzx/gpu-performance-revoked.json')
    raise
finally:
    if owned and PARAM.exists():
        (PARAM/'requested_mhz').write_text('200')
        subprocess.run(['rmmod', 'tzx_gpu_performance'], check=True, timeout=15)
    PENDING.unlink(missing_ok=True)
    actual = int(Path('/sys/kernel/debug/clk/gpu/clk_rate').read_text()) // 1000000
    atomic(STATUS, {'boot_id': BOOT, 'state': 'stopped', 'actual_mhz': actual})
