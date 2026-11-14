"""Exercise real-temperature thermal trips at lowered thresholds, then release QoS."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

assert os.geteuid() == 0
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert json.loads(Path('/var/lib/tzx/dram-gpu-boot-health.json').read_text())['boot_id'] == BOOT
assert Path('/sys/module/panfrost/parameters/tzx_dma32').read_text().strip() == 'Y'
module = Path('/home/debian/tzx_cpu_cooling.ko')
module_hash = hashlib.sha256(module.read_bytes()).hexdigest()
assert module_hash == 'd37b67d234a699a45eaf0c7f9c350123271754091a77c498a6f99e883ac37efa'
assert not Path('/sys/module/tzx_cpu_cooling').exists()
policies = [Path('/sys/devices/system/cpu/cpufreq')/f'policy{cpu}' for cpu in (0, 4)]
for policy in policies:
    assert (policy/'scaling_driver').read_text().strip() == 'tzx-a523-divider'
    assert (policy/'scaling_governor').read_text().strip() == 'schedutil'
    assert (policy/'scaling_max_freq').read_text().strip() == '480000'
work = Path('/home/debian/cpufreq-divider-trial/cpu-frequency-workload')
memory = Path('/home/debian/memory-check-bounded')
assert hashlib.sha256(work.read_bytes()).hexdigest() == '78ad0fd992c8bd9229a5ff7adf59c4d9eb5fff47d8a79e11644e32300985a7df'
assert hashlib.sha256(memory.read_bytes()).hexdigest() == '2f7ea0da43c78531b035dc330c8ef51d9764155e21d592679850b8ba0087f4f5'
children = []


def run(*command, timeout=35):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout).stdout


def observe(expected_state, expected_cap):
    actual = []
    for i in range(20):
        assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
        zones = {p.joinpath('type').read_text().strip(): p for p in Path('/sys/class/thermal').glob('thermal_zone*')}
        assert len(zones) == 6 and 'tzx-board-thermal' in zones
        values = {name: int((p/'temp').read_text()) for name, p in zones.items()}
        assert all(0 < t < 75000 for t in values.values()), values
        devices = {p.joinpath('type').read_text().strip(): p for p in Path('/sys/class/thermal').glob('cooling_device*')}
        assert set(devices) == {'tzx-cpu-cluster0', 'tzx-cpu-cluster1'}
        states = {name: int((p/'cur_state').read_text()) for name, p in devices.items()}
        caps = [int((p/'scaling_max_freq').read_text()) for p in policies]
        actual.append(dict(states=states, caps_kHz=caps, temperatures_mC=values))
        if list(states.values()) == [expected_state]*2 and caps == [expected_cap]*2:
            assert (zones['tzx-board-thermal']/'policy').read_text().strip() == 'step_wise'
            return actual[-1]
        time.sleep(0.5)
    raise AssertionError(actual)


def unload():
    if Path('/sys/module/tzx_cpu_cooling').exists():
        run('rmmod', 'tzx_cpu_cooling')
    for attempt in range(20):
        if all((p/'scaling_max_freq').read_text().strip() == '480000' for p in policies):
            break
        time.sleep(0.2)
    else:
        raise AssertionError('QoS maximum not released')
    assert len(list(Path('/sys/class/thermal').glob('thermal_zone*'))) == 5
    assert not list(Path('/sys/class/thermal').glob('cooling_device*'))


report = {'boot_id': BOOT, 'module_sha256': module_hash,
          'test': 'lower actual trip thresholds; no thermal emulation or heating',
          'cycles': [], 'PLL_DSU_voltage_changed': False}
run('systemd-run', '--unit=tzx-cooling-trial-independent-unload', '--on-active=4min',
    '/sbin/rmmod', 'tzx_cpu_cooling')
try:
    for state, cap, second in ((2, 120000, 31000), (1, 240000, 80000)):
        run('insmod', str(module), 'first_trip=30000', 'second_trip='+str(second))
        entry = observe(state, cap)
        workers = [subprocess.Popen([str(work), str(cpu)], stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT, text=True) for cpu in range(8)]
        children.extend(workers)
        for worker in workers:
            output = worker.communicate(timeout=20)[0]
            assert worker.returncode == 0 and json.loads(output)['checksum'] == 'a56490781b5a25dd', output
        observe(state, cap)
        output = run(str(memory), '256', timeout=35)
        assert 'MEMORY_TEST_256_MIB_8_THREADS_PASS' in output
        entry.update(workload_checksums_8='PASS', memory_256MiB='PASS', lowered_trips_mC=[30000, second])
        report['cycles'].append(entry)
        print('CPU_COOLING_REAL_TEMPERATURE_STEP_PASS', json.dumps(entry), flush=True)
        unload()
        print('CPU_COOLING_QOS_RELEASE_PASS', state, flush=True)
    run('insmod', str(module))
    normal = observe(0, 480000)
    report['production_defaults'] = dict(normal, trips_mC=[70000, 80000, 95000])
    zone = next(p for p in Path('/sys/class/thermal').glob('thermal_zone*')
                if (p/'type').read_text().strip() == 'tzx-board-thermal')
    assert [(zone/f'trip_point_{i}_temp').read_text().strip() for i in range(3)] == ['70000', '80000', '95000']
    assert all(len(list(zone.glob('cdev*trip_point'))) == 4 for _ in (0,))
    unload()
    output = run('python3', '/home/debian/verify_safe_memory.py', '--files-only', timeout=150)
    assert 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS' in output
    print(output, flush=True)
    report.update(result='PASS', file_audit='PASS', default_module_unloaded=True)
    target = Path('/var/lib/tzx/cpu-cooling-trial.json')
    temp = target.with_suffix('.new')
    with temp.open('w') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fchmod(stream.fileno(), 0o600)
        os.fsync(stream.fileno())
    temp.replace(target)
    directory = os.open(target.parent, os.O_DIRECTORY)
    os.fsync(directory)
    os.close(directory)
    print('CPU_COOLING_TWO_TRIPS_STANDARD_GOVERNOR_QOS_AND_RELEASE_PASS', json.dumps(report), flush=True)
finally:
    for process in children:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    unload()
    subprocess.run(['systemctl', 'stop', 'tzx-cooling-trial-independent-unload.timer'], check=True, timeout=20)
