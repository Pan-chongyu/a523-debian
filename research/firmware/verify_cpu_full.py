"""Bounded online CPU PLL tests; restore the qualified 480 MHz stack on exit."""
import array
import fcntl
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import signal
import statistics
import struct
import subprocess
import threading
import time

ROOT = Path('/home/debian/cpu-full')
assert hashlib.sha256((ROOT/'tzx_cpufreq_dvfs_v2.ko').read_bytes()).hexdigest() == 'f6187ea38bfaf5f57edd758839f0149489976465810548034b98007bc3787f64'
assert hashlib.sha256((ROOT/'tzx_cpu_dvfs_cooling_v2.ko').read_bytes()).hexdigest() == '6e26041ba4a0b28ef3824b04107e88746894cdfb01aa4aca1067e41da2c30daa'
subprocess.run(['systemctl', 'stop', 'tzx-emmc-hs.service'], check=True, timeout=55)
subprocess.run(['systemctl', 'stop', 'tzx-cpu-dvfs.service'], check=True, timeout=70)
subprocess.run(['systemctl', 'stop', 'tzx-cpu-performance.service'], check=True, timeout=45)
# ExecStopPost queues baseline startup. Wait for both the driver AND its
# cooler before changing governors; the cooler's startup asserts schedutil.
subprocess.run(['systemctl', 'start', 'tzx-cpufreq.service', 'tzx-cpu-cooling.service'], check=True, timeout=65)
for attempt in range(100):
    driver_path = Path('/sys/devices/system/cpu/cpufreq/policy4/scaling_driver')
    if driver_path.exists() and driver_path.read_text().strip() == 'tzx-a523-divider':
        break
    time.sleep(0.1)
else:
    raise AssertionError('Baseline driver did not restore')
for cluster in (0,4):
    policy = Path('/sys/devices/system/cpu/cpufreq')/('policy'+str(cluster))
    (policy/'scaling_min_freq').write_text('120000')
    (policy/'scaling_max_freq').write_text('480000')
    (policy/'scaling_governor').write_text('performance')
time.sleep(0.2)
lease_exit = threading.Event()
lease_enabled = threading.Event()
lease_enabled.set()
lease_thread = None
lease_error = []
def renew_loop():
    while not lease_exit.is_set():
        if lease_enabled.is_set() and Path('/sys/module/tzx_cpufreq_dvfs_v2/parameters/renew').exists():
            try:
                Path('/sys/module/tzx_cpufreq_dvfs_v2/parameters/renew').write_text('1')
            except BaseException as error:
                lease_error.append(repr(error))
        stop_ping.wait(1)

POLICIES = [Path('/sys/devices/system/cpu/cpufreq')/('policy'+str(n)) for n in (0, 4)]
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
WORK = Path('/home/debian/cpufreq-divider-trial/cpu-frequency-workload')
MEMORY = Path('/home/debian/memory-check-bounded')
assert hashlib.sha256(WORK.read_bytes()).hexdigest() == '78ad0fd992c8bd9229a5ff7adf59c4d9eb5fff47d8a79e11644e32300985a7df'
assert hashlib.sha256(MEMORY.read_bytes()).hexdigest() == '2f7ea0da43c78531b035dc330c8ef51d9764155e21d592679850b8ba0087f4f5'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
peaks = {}
records = []
children = []
started = time.monotonic()
stop_ping = threading.Event()
watchdog = None
ping_thread = None
outcome = None
replaced = False
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
registers = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x08817000)
offsets = (0, 4, 8, 12, 0x60, 0x64, 0x68, 0x6c)
initial = {offset: struct.unpack_from('<I', registers, offset)[0] for offset in offsets}
sentinel = os.urandom(128*1024*1024)
sentinel_hash = hashlib.sha256(sentinel).digest()

def run(*command, timeout=45):
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT, timeout=timeout)

def voltage():
    record = json.loads(run('python3', '/usr/local/lib/tzx-dram-gpu/read_axp_dram_status.py'))
    return {name: record[name] for name in ('axp717', 'axp323', 'dcdc3_setpoint_mV')}

before_voltage = voltage()
assert all(int(before_voltage['axp717'][r], 16) & 127 == 40 for r in ('0x83', '0x84'))
assert all(int(before_voltage['axp323'][r], 16) & 127 == 40 for r in ('0x13', '0x14', '0x15'))

def state(stage, **extra):
    record = {'stage': stage, 'boot_id': BOOT, 'elapsed': round(time.monotonic()-started, 2),
              'records': records, 'peaks_mc': peaks, **extra}
    with (ROOT/'trial-state.json').open('w') as stream:
        stream.write(json.dumps(record,indent=2)+'\n');stream.flush();os.fsync(stream.fileno())
    print(stage, json.dumps(extra), flush=True)

def guard():
    assert time.monotonic()-started < 720
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    assert hashlib.sha256(sentinel).digest() == sentinel_hash, 'RAM sentinel changed'
    if Path('/sys/module/tzx_cpufreq_dvfs_v2').exists():
        assert int(Path('/sys/module/tzx_cpufreq_dvfs_v2/parameters/clock_fault').read_text()) == 0
    faults = [s for s in run('dmesg').splitlines()
              if re.search(r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b', s, re.I)]
    assert not faults, faults
    assert not lease_error, lease_error
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        name = (zone/'type').read_text().strip()
        temperature = int((zone/'temp').read_text())
        assert 0 < temperature < 75000, (name, temperature)
        peaks[name] = max(peaks.get(name, 0), temperature)
    for offset in (0, 8, 0x68, 0x6c):
        assert struct.unpack_from('<I', registers, offset)[0] == initial[offset], hex(offset)

def tune(cluster, frequency, governor='performance'):
    policy = POLICIES[cluster]
    (policy/'scaling_min_freq').write_text('120000')
    (policy/'scaling_max_freq').write_text(str(frequency))
    (policy/'scaling_governor').write_text(governor)
    if governor == 'performance':
        (policy/'scaling_min_freq').write_text(str(frequency))
        for attempt in range(30):
            if int((policy/'scaling_cur_freq').read_text()) == frequency:
                break
            time.sleep(0.05)
        else:
            raise AssertionError(('frequency did not settle', cluster, frequency))
        pll = struct.unpack_from('<I', registers, (4, 12)[cluster])[0]
        mux = struct.unpack_from('<I', registers, (0x60, 0x64)[cluster])[0]
        assert ((mux >> 24) & 7) == 3
        actual = 24000 * ((pll >> 8) & 255) >> ((mux >> 16) & 3)
        assert actual == frequency, (hex(pll), hex(mux), actual, frequency)
    guard()

def benchmark(cpu, count=3):
    values = [json.loads(run(str(WORK), str(cpu), timeout=15)) for _ in range(count)]
    assert all(v['checksum'] == 'a56490781b5a25dd' for v in values), values
    return {'cpu': cpu, 'median_thread_seconds': statistics.median(v['thread_seconds'] for v in values),
            'samples': values}

def workload(command, name, timeout=70):
    path = ROOT/(name+'.log')
    with path.open('w') as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
        children.append(process)
        limit = time.monotonic()+timeout
        while process.poll() is None:
            guard()
            assert time.monotonic() < limit, ('workload deadline', name)
            time.sleep(0.5)
        assert process.returncode == 0, (name, process.returncode, path.read_text()[-1000:])
    return path.read_text()

def ping():
    while not stop_ping.wait(2):
        os.write(watchdog, b'.')

def interrupt(signum, frame):
    raise RuntimeError('Interrupted by signal '+str(signum))

signal.signal(signal.SIGTERM, interrupt)
signal.signal(signal.SIGINT, interrupt)
try:
    watchdog = os.open('/dev/watchdog', os.O_WRONLY | os.O_CLOEXEC)
    support = bytearray(40)
    fcntl.ioctl(watchdog, 0x80285700, support, True)
    assert int.from_bytes(support[:4], 'little') & 0x100
    timeout = array.array('i', [16])
    fcntl.ioctl(watchdog, 0xc0045706, timeout, True)
    assert timeout[0] >= 10
    ping_thread = threading.Thread(target=ping, daemon=True)
    ping_thread.start()
    state('BASELINE')
    for cluster in (0, 1):
        tune(cluster, 480000)
        records.append(dict(stage='baseline', khz=480000, **benchmark(cluster*4)))
    state('REPLACING_DRIVER')
    run('systemctl', 'stop', 'tzx-cpu-cooling.service')
    run('systemctl', 'stop', 'tzx-cpufreq.service')
    replaced = True
    assert not list(Path('/sys/devices/system/cpu/cpufreq').glob('policy*'))
    run('insmod', str(ROOT/'tzx_cpufreq_dvfs_v2.ko'), 'lease_seconds=5')
    Path('/sys/module/tzx_cpufreq_dvfs_v2/parameters/renew').write_text('1')
    lease_thread = threading.Thread(target=renew_loop, daemon=True)
    lease_thread.start()
    assert Path('/sys/devices/system/cpu/online').read_text().strip()=='0-7'
    capacities=[int(Path('/sys/devices/system/cpu/cpu%d/cpu_capacity'%i).read_text()) for i in range(8)]
    assert capacities==[725]*4+[1024]*4,capacities
    state('NORMALIZED_SCHEDULER_CAPACITY',capacities=capacities)

    assert all(int((p/'scaling_max_freq').read_text()) == 480000 for p in POLICIES)
    run('insmod', str(ROOT/'tzx_cpu_dvfs_cooling_v2.ko'))
    for cluster, frequencies in ((1, (480000, 1008000, 1200000, 1344000, 1488000, 1584000, 1680000, 1800000)),
                                 (0, (480000, 792000, 1008000, 1224000, 1416000))):
        tune(1-cluster, 120000)
        for frequency in frequencies:
            state('FREQUENCY_STEP', cluster=cluster, khz=frequency)
            tune(cluster, frequency)
            observed_voltage = voltage()
            expected = (900 if frequency <= 1008000 else 920 if frequency == 1200000 else 960 if frequency == 1344000 else 1000 if frequency == 1488000 else 1050 if frequency == 1584000 else 1100 if frequency == 1680000 else 1150) if cluster else (900 if frequency <= 792000 else 960 if frequency == 1008000 else 1050 if frequency == 1224000 else 1150)
            key, register = ('axp717','0x83') if not cluster else ('axp323','0x13')
            assert 500+(int(observed_voltage[key][register],16)&127)*10 == expected, observed_voltage
            for name, registers_to_check in (('axp717', ('0x3','0x80','0x84','0x85','0x86','0x98')), ('axp323', ('0x3','0x10','0x14','0x15'))):
                assert all(observed_voltage[name][r] == before_voltage[name][r] for r in registers_to_check), observed_voltage
            records.append(dict(stage='new-driver', khz=frequency, millivolts=expected, **benchmark(cluster*4)))
            guard()
    tune(0, 1416000)
    tune(1, 1800000)
    state('EIGHT_CORE_CHECKSUMS')
    for repeat in range(5):
        workers = [subprocess.Popen([str(WORK), str(cpu)], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True) for cpu in range(8)]
        children.extend(workers)
        while any(p.poll() is None for p in workers):
            guard()
            time.sleep(0.2)
        for worker in workers:
            output = worker.communicate(timeout=5)[0]
            assert worker.returncode == 0 and json.loads(output)['checksum'] == 'a56490781b5a25dd', output
    state('RAM_AND_EXECUTION')
    for repeat in range(3):
        text = workload([str(MEMORY), '512'], 'memory-512MiB-'+str(repeat+1))
        assert 'MEMORY_TEST_512_MIB_8_THREADS_PASS' in text, text
    text = workload(['/home/debian/cpu-full/cpu-dvfs-execution'], 'execution-coherency')
    assert 'PASS' in text, text

    state('COOL_BEFORE_TRANSITIONS')
    for cluster in (0,1): tune(cluster,480000,'schedutil')
    cooling_deadline=time.monotonic()+90
    while max(int((p/'temp').read_text()) for p in Path('/sys/class/thermal').glob('thermal_zone*'))>60000:
        guard()
        assert time.monotonic()<cooling_deadline,'Cooling deadline'
        time.sleep(1)
    state('CLOCK_TRANSITIONS')
    for repeat in range(20):
        for frequency in (120000, 480000, 1008000, 1416000):
            tune(0, frequency)
            tune(1, 1800000 if frequency == 1416000 else frequency)
    state('GPU_COEXISTENCE')
    tune(0, 1416000)
    tune(1, 1800000)
    text = workload(['runuser', '-u', 'debian', '--', 'env', 'DISPLAY=:0',
                     'XAUTHORITY=/home/debian/.Xauthority', 'glmark2-es2', '--size', '640x480',
                     '--off-screen', '-b', ':duration=1'], 'gpu-cpu-performance')
    assert 'Mali-G57 (Panfrost)' in text and 'Error:' not in text
    gpu_score = int(re.search(r'glmark2 Score:\s*(\d+)', text)[1])
    state('THERMAL_QOS')
    for policy in POLICIES:
        (policy/'scaling_min_freq').write_text('120000')
    run('rmmod', 'tzx_cpu_dvfs_cooling_v2')
    run('insmod', str(ROOT/'tzx_cpu_dvfs_cooling_v2.ko'), 'first_trip=30000', 'second_trip=31000')
    for attempt in range(30):
        if all(int((p/'scaling_max_freq').read_text()) == 240000 for p in POLICIES):
            break
        time.sleep(0.5)
    else:
        raise AssertionError('Thermal QoS did not cap both clusters')
    # Remove per-user high minimums so they do not mask the lower thermal cap.
    for policy in POLICIES:
        (policy/'scaling_min_freq').write_text('120000')
    guard()
    assert all(int((p/'scaling_cur_freq').read_text()) <= 240000 for p in POLICIES)
    run('rmmod', 'tzx_cpu_dvfs_cooling_v2')
    run('insmod', str(ROOT/'tzx_cpu_dvfs_cooling_v2.ko'))
    state('SCHEDUTIL_IDLE_LOAD_IDLE')
    for cluster, maximum in enumerate((1416000, 1800000)):
        tune(cluster, maximum, 'schedutil')
    idle = []
    for sample in range(25):
        idle.append([int((p/'scaling_cur_freq').read_text()) for p in POLICIES])
        time.sleep(0.2)
    assert all(min(row[i] for row in idle) < 480000 for i in range(2)), idle
    state('LEASE_EXPIRY')
    for cluster in (0,1):
        tune(cluster, (1416000,1800000)[cluster], 'performance')
        (POLICIES[cluster]/'scaling_min_freq').write_text('120000')
    lease_enabled.clear()
    time.sleep(7)
    assert all(int((p/'scaling_cur_freq').read_text()) <= 480000 for p in POLICIES)
    assert voltage() == before_voltage, 'Lease expiry did not restore 900mV'
    assert Path('/sys/module/tzx_cpufreq_dvfs_v2/parameters/lease_active').read_text().strip() == '0'
    lease_enabled.set()
    Path('/sys/module/tzx_cpufreq_dvfs_v2/parameters/renew').write_text('1')
    guard()
    outcome = {'status': 'PASS', 'boot_id': BOOT, 'records': records, 'peaks_mc': peaks,
               'gpu_score': gpu_score, 'memory_512MiB_passes': 3, 'eight_core_checksums': 40,
               'clock_transitions': 160, 'thermal_qos_240MHz': 'PASS',
               'idle_minimum_khz': [min(row[i] for row in idle) for i in range(2)],
               'pmic_before_and_after_lease_expiry': before_voltage, 'lease_expiry_480MHz_900mV': 'PASS', 'DSU_backup_PLL_gates_unchanged': True,
               'kernel_taint': 4096, 'speed_bin': 'vf0300', 'capacity': capacities, 'ram_sentinel_bytes': len(sentinel)}
except BaseException as error:
    state('FAILED', error=repr(error))
    raise
finally:
    try:
        for child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        lease_enabled.clear()
        lease_exit.set()
        if lease_thread:
            lease_thread.join(timeout=3)
        # Keep the watchdog fed while restoring modules and services.
        if watchdog is not None:
            os.write(watchdog, b'.')
        if replaced:
            if Path('/sys/module/tzx_cpu_dvfs_cooling_v2').exists():
                run('rmmod', 'tzx_cpu_dvfs_cooling_v2')
            if Path('/sys/module/tzx_cpufreq_dvfs_v2').exists():
                run('rmmod', 'tzx_cpufreq_dvfs_v2')
            for offset in offsets:
                observed = struct.unpack_from('<I', registers, offset)[0]
                if offset in (0x60, 0x64):
                    assert observed & ~(3 << 16) == initial[offset] & ~(3 << 16), (hex(offset), hex(observed))
                elif offset in (4, 12):
                    assert observed & ~((1 << 28) | (1 << 26)) == initial[offset] & ~((1 << 28) | (1 << 26)), (hex(offset), hex(observed))
                else:
                    assert observed == initial[offset], hex(offset)
            run('systemctl', 'start', 'tzx-cpufreq.service')
            run('systemctl', 'start', 'tzx-cpu-cooling.service')
            assert voltage() == before_voltage, 'Unload did not restore all PMIC registers'
            run('systemctl', 'start', 'tzx-cpu-dvfs.service',timeout=85)
        else:
            for policy in POLICIES:
                (policy/'scaling_min_freq').write_text('120000')
                (policy/'scaling_max_freq').write_text('480000')
                (policy/'scaling_governor').write_text('schedutil')
    finally:
        stop_ping.set()
        if ping_thread:
            ping_thread.join(timeout=5)
        if watchdog is not None:
            os.write(watchdog, b'V')
            os.close(watchdog)
        registers.close()
        os.close(fd)
if outcome is not None:
    outcome['baseline_restored'] = True
    outcome['elapsed'] = round(time.monotonic()-started, 2)
    (ROOT/'trial-result.json').write_text(json.dumps(outcome, indent=2)+'\n')
    state('CPU_DVFS_TRIAL_PASS', result=outcome)
