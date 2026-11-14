"""Exercise independent cluster frequencies, actual speed, RAM and unload."""
import hashlib
import json
import mmap
import os
from pathlib import Path
import statistics
import struct
import subprocess
import time

assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert not Path('/sys/module/panfrost').exists()
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert not Path('/sys/module/tzx_cpufreq_divider').exists()
root = Path('/home/debian/cpufreq-divider-trial')
manifest = json.loads((root / 'FILES.json').read_text())
for name, digest in manifest.items():
    assert '/' not in name and hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
module = root / 'tzx_cpufreq_divider.ko'
benchmark = root / 'cpu-frequency-workload'
benchmark.chmod(0o755)
(root / 'memory-check-bounded').chmod(0o755)
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
offsets = (0, 4, 8, 12, 0x60, 0x64, 0x68, 0x6c)


def registers():
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    try:
        with mmap.mmap(fd, 4096, prot=mmap.PROT_READ, offset=0x08817000) as regs:
            return {hex(i): struct.unpack_from('<I', regs, i)[0] for i in offsets}
    finally:
        os.close(fd)


def guard():
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    values = {p.name: int((p / 'temp').read_text()) for p in Path('/sys/class/thermal').glob('thermal_zone*')}
    assert len(values) == 5 and max(values.values()) < 75000, values
    return values


def run(*command, timeout=45):
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    if result.stdout.strip():
        print(result.stdout.strip(), flush=True)
    if result.stderr.strip():
        print(result.stderr.strip(), flush=True)
    result.check_returncode()
    return result.stdout


before = registers()
Path('/run/tzx-cpufreq-before.json').write_text(json.dumps({'boot_id': boot, 'registers': before}))
run('systemd-run', '--unit=tzx-cpufreq-independent-rollback', '--on-active=6min',
    '/usr/bin/python3', '/home/debian/cleanup_cpufreq_divider.py')
report = {'boot_id': boot, 'before': before, 'cycles': [], 'frequency_limit_kHz': 480000,
          'PLL_DSU_voltage_changed': False, 'persistent_enablement': False}
checksum = None
try:
    for cycle in range(2):
        run('insmod', str(module))
        policies = sorted(Path('/sys/devices/system/cpu/cpufreq').glob('policy*'))
        assert [p.name for p in policies] == ['policy0', 'policy4'], policies
        for cluster, policy in enumerate(policies):
            assert (policy / 'scaling_driver').read_text().strip() == 'tzx-a523-divider'
            assert [int(x) for x in (policy / 'related_cpus').read_text().split()] == list(range(cluster*4, cluster*4+4))
            assert set((policy / 'scaling_available_frequencies').read_text().split()) == {'120000', '240000', '480000'}
            (policy / 'scaling_governor').write_text('userspace')
        current = {0: 480000, 1: 480000}
        results = {}
        for cluster, policy in enumerate(policies):
            measurements = {}
            for frequency in (480000, 240000, 120000, 480000):
                guard()
                (policy / 'scaling_setspeed').write_text(str(frequency))
                current[cluster] = frequency
                time.sleep(0.08)
                actual = registers()
                for offset in offsets:
                    name = hex(offset)
                    if offset not in (0x60, 0x64):
                        assert actual[name] == before[name], (name, actual, before)
                for other in (0, 1):
                    offset = (0x60, 0x64)[other]
                    divider = {480000: 0, 240000: 1, 120000: 2}[current[other]]
                    assert actual[hex(offset)] == (before[hex(offset)] & ~(3 << 16)) | (divider << 16)
                    assert int((policies[other] / 'cpuinfo_cur_freq').read_text()) == current[other]
                runs = [json.loads(run(str(benchmark), str(cluster*4))) for _ in range(2)]
                for item in runs:
                    if checksum is None:
                        checksum = item['checksum']
                    assert item['checksum'] == checksum
                measurements.setdefault(frequency, []).extend(x['thread_seconds'] for x in runs)
                print('CPUFREQ_CLUSTER_MEASURED', json.dumps({'cycle': cycle+1, 'cluster': cluster,
                    'frequency_kHz': frequency, 'samples': runs, 'registers': actual}), flush=True)
            median = {freq: statistics.median(samples) for freq, samples in measurements.items()}
            assert 1.5 < median[240000] / median[480000] < 2.7, median
            assert 2.8 < median[120000] / median[480000] < 5.5, median
            results[str(cluster)] = median
        for frequency in (120000, 240000, 480000):
            for policy in policies:
                (policy / 'scaling_setspeed').write_text(str(frequency))
            memory = run(str(root / 'memory-check-bounded'), '128', timeout=100)
            assert 'MEMORY_TEST_128_MIB_8_THREADS_PASS' in memory
            guard()
        for policy in policies:
            (policy / 'scaling_setspeed').write_text('480000')
        run('rmmod', 'tzx_cpufreq_divider')
        assert registers() == before
        assert not list(Path('/sys/devices/system/cpu/cpufreq').glob('policy*'))
        report['cycles'].append({'cycle': cycle+1, 'measured_thread_seconds': results,
                                 'all_three_frequencies_RAM_128MiB': 'PASS', 'unload_restore': 'PASS'})
        print('CPUFREQ_DIVIDER_CYCLE_PASS', json.dumps(report['cycles'][-1]), flush=True)
    report['result'] = 'PASS'
    Path('/home/debian/cpufreq-divider-trial.json').write_text(json.dumps(report, indent=2) + '\n')
    os.sync()
    print('CPUFREQ_TWO_LOADS_INDEPENDENT_CLUSTERS_ACTUAL_SPEED_RAM_AND_UNLOAD_PASS', json.dumps(report), flush=True)
finally:
    run('python3', '/home/debian/cleanup_cpufreq_divider.py')
