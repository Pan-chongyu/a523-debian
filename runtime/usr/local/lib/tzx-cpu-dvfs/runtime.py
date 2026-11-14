"""Online CPU performance ownership with a pinned 480 MHz recovery path."""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

ROOT = Path('/usr/local/lib/tzx-cpu-dvfs')
QUALIFIED = Path('/var/lib/tzx/cpu-dvfs-qualified.json')
PENDING = Path('/var/lib/tzx/cpu-dvfs-pending.json')
STATUS = Path('/run/tzx-cpu-dvfs.json')
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
POLICIES = [Path('/sys/devices/system/cpu/cpufreq')/('policy'+str(n)) for n in (0, 4)]
quit_event = threading.Event()
assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == Path('/etc/tzx/device-cid').read_text().strip()
assert len(sys.argv) == 2 and sys.argv[1] in ('run', 'restore')

def run(*command, timeout=60):
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT, timeout=timeout)

def atomic(path, value):
    temporary = path.with_suffix(path.suffix+'.new')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)

def restore():
    if Path('/sys/module/tzx_cpu_dvfs_cooling').exists():
        run('rmmod', 'tzx_cpu_dvfs_cooling')
    if Path('/sys/module/tzx_cpufreq_dvfs').exists():
        run('rmmod', 'tzx_cpufreq_dvfs')
    manager = subprocess.run(['systemctl', 'is-system-running'], capture_output=True, text=True).stdout.strip()
    if manager != 'stopping':
        # These units are ordered before this service. During an explicit
        # stop their start jobs wait for our stop to complete: waiting here
        # would deadlock. Queue the transaction and let ExecStopPost exit.
        run('systemctl', '--no-block', 'start', 'tzx-cpufreq.service', 'tzx-cpu-cooling.service')
    PENDING.unlink(missing_ok=True)
    atomic(STATUS, {'boot_id': BOOT, 'state': 'restoring-baseline', 'maximum_khz': [480000, 480000]})

if sys.argv[1] == 'restore':
    restore()
    print('CPU_PERFORMANCE_ORIGINAL_DRIVER_AND_THERMAL_POLICY_RESTORED', flush=True)
    raise SystemExit(0)

def signal_stop(signum, frame):
    quit_event.set()

signal.signal(signal.SIGTERM, signal_stop)
signal.signal(signal.SIGINT, signal_stop)
try:
    manifest = json.loads((ROOT/'manifest.json').read_text())
    for name, digest in manifest['files'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    qualification = json.loads(QUALIFIED.read_text())
    assert qualification['trial']['status'] == 'PASS' and qualification['trial']['baseline_restored']
    if PENDING.exists():
        assert json.loads(PENDING.read_text())['boot_id'] == BOOT, 'Unclean previous CPU performance boot'
    run('python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard')
    health = json.loads(Path('/var/lib/tzx/dram-gpu-boot-health.json').read_text())
    assert health['boot_id'] == BOOT and health['status'] == 'PASS'
    voltage = json.loads(run('python3', '/usr/local/lib/tzx-dram-gpu/read_axp_dram_status.py'))
    for chip, names in (('axp717', ('0x83', '0x84')), ('axp323', ('0x13', '0x14', '0x15'))):
        assert all(int(voltage[chip][r], 16) & 127 == 40 for r in names)
    assert voltage['dcdc3_setpoint_mV'] == 1260
    atomic(PENDING, {'boot_id': BOOT, 'state': 'running', 'maximum_khz': [1416000, 1488000]})
    run('systemctl', 'stop', 'tzx-cpu-performance.service')
    run('systemctl', 'start', 'tzx-cpufreq.service', 'tzx-cpu-cooling.service')
    run('systemctl', 'stop', 'tzx-cpu-cooling.service')
    run('systemctl', 'stop', 'tzx-cpufreq.service')
    run('insmod', str(ROOT/'tzx_cpufreq_dvfs.ko'))
    Path('/sys/module/tzx_cpufreq_dvfs/parameters/renew').write_text('1')
    run('insmod', str(ROOT/'tzx_cpu_dvfs_cooling.ko'))
    for name, value in (('first_trip', '70000'), ('second_trip', '80000')):
        assert (Path('/sys/module/tzx_cpu_dvfs_cooling/parameters')/name).read_text().strip() == value
    for index, policy in enumerate(POLICIES):
        assert (policy/'scaling_driver').read_text().strip() == 'tzx-a523-dvfs'
        (policy/'scaling_min_freq').write_text('120000')
        (policy/'scaling_max_freq').write_text(str((1416000, 1488000)[index]))
        (policy/'scaling_governor').write_text('schedutil')
    voltage_checked = time.monotonic()
    while not quit_event.is_set():
        Path('/sys/module/tzx_cpufreq_dvfs/parameters/renew').write_text('1')
        assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
        assert int(Path('/sys/module/tzx_cpufreq_dvfs/parameters/clock_fault').read_text()) == 0
        errors = [s for s in run('dmesg').splitlines()
                  if re.search(r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b', s, re.I)]
        assert not errors, errors
        values = {p.joinpath('type').read_text().strip(): int(p.joinpath('temp').read_text())
                  for p in Path('/sys/class/thermal').glob('thermal_zone*')}
        assert len(values) == 6 and all(0 < t < 85000 for t in values.values())
        if time.monotonic()-voltage_checked >= 60:
            observed = json.loads(run('python3', '/usr/local/lib/tzx-dram-gpu/read_axp_dram_status.py'))
            assert observed['dcdc3_setpoint_mV'] == voltage['dcdc3_setpoint_mV'] == 1260
            for chip, changed, ceiling in (('axp717','0x83',65),('axp323','0x13',50)):
                assert all(observed[chip][key] == value for key,value in voltage[chip].items() if key != changed)
                selector = int(observed[chip][changed],16)
                assert selector & 128 == int(voltage[chip][changed],16) & 128
                assert 40 <= (selector & 127) <= ceiling
            voltage_checked = time.monotonic()
        state = {'boot_id': BOOT, 'state': 'active', 'maximum_khz': [1416000, 1488000],
                 'actual_khz': [int((p/'scaling_cur_freq').read_text()) for p in POLICIES],
                 'CPU_DCDC1_setpoint_mV': Path('/sys/module/tzx_cpufreq_dvfs/parameters/rail_mv').read_text().strip(),
                 'lease_seconds': 30,
                 'effective_maximum_khz': [int((p/'scaling_max_freq').read_text()) for p in POLICIES],
                 'governors': [(p/'scaling_governor').read_text().strip() for p in POLICIES],
                 'temperatures_mc': values, 'voltage_changed': True, 'CPU_DCDC1_only': True, 'DSU_changed': False,
                 'thermal_caps_khz': ['cluster maximum', 480000, 240000],
                 'thermal_trips_mc': [70000, 80000, 95000]}
        atomic(STATUS, state)
        quit_event.wait(5)
except BaseException as error:
    atomic(Path('/var/lib/tzx/cpu-dvfs-failure.json'), {'boot_id': BOOT, 'error': repr(error)})
    if QUALIFIED.exists():
        QUALIFIED.replace('/var/lib/tzx/cpu-dvfs-revoked.json')
    raise
finally:
    restore()
