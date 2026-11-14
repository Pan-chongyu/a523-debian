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

ROOT = Path('/home/debian/cpu-performance')
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
    (ROOT/'trial-state.json').write_text(json.dumps(record, indent=2)+'\n')
    print(stage, json.dumps(extra), flush=True)

def guard():
    assert time.monotonic()-started < 720
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    assert hashlib.sha256(sentinel).digest() == sentinel_hash, 'RAM sentinel changed'
    if Path('/sys/module/tzx_cpufreq_safepll').exists():
        assert int(Path('/sys/module/tzx_cpufreq_safepll/parameters/clock_fault').read_text()) == 0
    faults = [s for s in run('dmesg').splitlines()
              if re.search(r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b', s, re.I)]
    assert not faults, faults
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        name = (zone/'type').read_text().strip()
        temperature = int((zone/'temp').read_text())
        assert 0 < temperature < 65000, (name, temperature)
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
    run('insmod', str(ROOT/'tzx_cpufreq_safepll.ko'))
    assert all(int((p/'scaling_max_freq').read_text()) == 480000 for p in POLICIES)
    run('insmod', str(ROOT/'tzx_cpu_perf_cooling.ko'))
    for cluster, frequencies in ((1, (480000, 600000, 792000, 1008000)),
                                 (0, (480000, 600000, 792000))):
        for frequency in frequencies:
            state('FREQUENCY_STEP', cluster=cluster, khz=frequency)
            tune(cluster, frequency)
            records.append(dict(stage='new-driver', khz=frequency, **benchmark(cluster*4)))
            guard()
    tune(0, 792000)
    tune(1, 1008000)
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
    text = workload(['/home/debian/cpu-execution-coherency'], 'execution-coherency')
    assert 'PASS' in text, text
    state('CLOCK_TRANSITIONS')
    for repeat in range(20):
        for frequency in (120000, 480000, 600000, 792000):
            tune(0, frequency)
            tune(1, 1008000 if frequency == 792000 else frequency)
    state('GPU_COEXISTENCE')
    tune(0, 792000)
    tune(1, 1008000)
    text = workload(['runuser', '-u', 'debian', '--', 'env', 'DISPLAY=:0',
                     'XAUTHORITY=/home/debian/.Xauthority', 'glmark2-es2', '--size', '640x480',
                     '--off-screen', '-b', ':duration=1'], 'gpu-cpu-performance')
    assert 'Mali-G57 (Panfrost)' in text and 'Error:' not in text
    gpu_score = int(re.search(r'glmark2 Score:\s*(\d+)', text)[1])
    state('THERMAL_QOS')
    for policy in POLICIES:
        (policy/'scaling_min_freq').write_text('120000')
    run('rmmod', 'tzx_cpu_perf_cooling')
    run('insmod', str(ROOT/'tzx_cpu_perf_cooling.ko'), 'first_trip=30000', 'second_trip=31000')
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
    run('rmmod', 'tzx_cpu_perf_cooling')
    run('insmod', str(ROOT/'tzx_cpu_perf_cooling.ko'))
    state('SCHEDUTIL_IDLE_LOAD_IDLE')
    for cluster, maximum in enumerate((792000, 1008000)):
        tune(cluster, maximum, 'schedutil')
    idle = []
    for sample in range(25):
        idle.append([int((p/'scaling_cur_freq').read_text()) for p in POLICIES])
        time.sleep(0.2)
    assert all(min(row[i] for row in idle) < 480000 for i in range(2)), idle
    assert voltage() == before_voltage, 'PMIC settings changed'
    guard()
    outcome = {'status': 'PASS', 'boot_id': BOOT, 'records': records, 'peaks_mc': peaks,
               'gpu_score': gpu_score, 'memory_512MiB_passes': 3, 'eight_core_checksums': 40,
               'clock_transitions': 160, 'thermal_qos_240MHz': 'PASS',
               'idle_minimum_khz': [min(row[i] for row in idle) for i in range(2)],
               'pmic_before_after': before_voltage, 'DSU_backup_PLL_gates_unchanged': True,
               'kernel_taint': 4096, 'ram_sentinel_bytes': len(sentinel)}
except BaseException as error:
    state('FAILED', error=repr(error))
    raise
finally:
    for child in children:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
    if replaced:
        if Path('/sys/module/tzx_cpu_perf_cooling').exists():
            run('rmmod', 'tzx_cpu_perf_cooling')
        if Path('/sys/module/tzx_cpufreq_safepll').exists():
            run('rmmod', 'tzx_cpufreq_safepll')
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
    else:
        for policy in POLICIES:
            (policy/'scaling_min_freq').write_text('120000')
            (policy/'scaling_max_freq').write_text('480000')
            (policy/'scaling_governor').write_text('schedutil')
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
    state('CPU_PERFORMANCE_TRIAL_PASS', result=outcome)
