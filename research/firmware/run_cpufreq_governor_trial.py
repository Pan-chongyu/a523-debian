"""Verify schedutil changes actual dividers with load and preserves data integrity."""
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import time

assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert not Path('/sys/module/panfrost').exists()
assert not Path('/sys/module/tzx_cpufreq_divider').exists()
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
manual = json.loads(Path('/home/debian/cpufreq-divider-trial.json').read_text())
assert manual['result'] == 'PASS' and len(manual['cycles']) == 2 and manual['boot_id'] == boot
root = Path('/home/debian/cpufreq-divider-trial')
module = root / 'tzx_cpufreq_divider.ko'
work = root / 'cpu-frequency-workload'
memory = root / 'memory-check-bounded'
for path, digest in ((module, '95a0d572d6a363b1b70984cf51e2ae6dff7e8470fc3a2e66072af5a8a508903c'),
                     (work, '78ad0fd992c8bd9229a5ff7adf59c4d9eb5fff47d8a79e11644e32300985a7df'),
                     (memory, '2f7ea0da43c78531b035dc330c8ef51d9764155e21d592679850b8ba0087f4f5')):
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    if path != module:
        path.chmod(0o755)
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
regs = mmap.mmap(fd, 4096, prot=mmap.PROT_READ, offset=0x08817000)
baseline = {int(name, 16): value for name, value in manual['before'].items()}
peaks = {}
processes = []

def sample():
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    values = {}
    for offset, before in baseline.items():
        value = struct.unpack_from('<I', regs, offset)[0]
        if offset in (0x60, 0x64):
            assert value & ~(3 << 16) == before & ~(3 << 16)
            divider = (value >> 16) & 3
            assert divider in (0, 1, 2)
            values[str(offset)] = 480000 >> divider
        else:
            assert value == before, (hex(offset), hex(value), hex(before))
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        value = int((zone / 'temp').read_text())
        assert 0 < value < 75000
        peaks[zone.name] = max(peaks.get(zone.name, 0), value)
    return values

def idle(seconds):
    history = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        history.append(sample())
        time.sleep(0.1)
    return history

report = {'boot_id': boot, 'cycles': [], 'module_sha256': hashlib.sha256(module.read_bytes()).hexdigest(),
          'maximum_kHz': 480000, 'PLL_DSU_voltage_changed': False, 'persistent_enablement': False}
subprocess.run(['systemd-run', '--unit=tzx-cpufreq-independent-rollback', '--on-active=6min',
                '/usr/bin/python3', '/home/debian/cleanup_cpufreq_divider.py'], check=True)
try:
    subprocess.run(['insmod', str(module)], check=True)
    policies = [Path('/sys/devices/system/cpu/cpufreq') / f'policy{cpu}' for cpu in (0, 4)]
    for policy in policies:
        assert (policy / 'scaling_driver').read_text().strip() == 'tzx-a523-divider'
        (policy / 'scaling_min_freq').write_text('120000')
        (policy / 'scaling_max_freq').write_text('480000')
        (policy / 'scaling_governor').write_text('schedutil')
    for cycle in range(2):
        quiet = idle(7)
        low = {name: min(row[name] for row in quiet) for name in ('96', '100')}
        assert all(value < 480000 for value in low.values()), low
        busy = []
        for repeat in range(10):
            processes = [subprocess.Popen([str(work), str(cpu)], stdout=subprocess.PIPE,
                                          stderr=subprocess.STDOUT, text=True) for cpu in range(8)]
            while any(process.poll() is None for process in processes):
                busy.append(sample())
                time.sleep(0.1)
            for process in processes:
                output = process.communicate(timeout=5)[0]
                assert process.returncode == 0, output
                row = json.loads(output)
                assert row['checksum'] == 'a56490781b5a25dd', row
            processes = []
        high = {name: max(row[name] for row in busy) for name in ('96', '100')}
        assert all(value == 480000 for value in high.values()), high
        after = idle(7)
        restored_low = {name: min(row[name] for row in after) for name in ('96', '100')}
        assert all(value < 480000 for value in restored_low.values()), restored_low
        entry = dict(cycle=cycle+1, quiet_minimum_kHz=low, load_maximum_kHz=high,
                     quiet_after_minimum_kHz=restored_low, workloads=80,
                     all_workload_checksums='PASS', samples=len(quiet)+len(busy)+len(after))
        report['cycles'].append(entry)
        print('CPUFREQ_SCHEDUTIL_IDLE_LOAD_IDLE_PASS', json.dumps(entry), flush=True)
    result = subprocess.run([str(memory), '2560'], capture_output=True, text=True, timeout=80)
    print(result.stdout, end='', flush=True)
    assert result.returncode == 0 and 'MEMORY_TEST_2560_MIB_8_THREADS_PASS' in result.stdout
    report['memory_2560MiB'] = 'PASS'
    sample()
    result = subprocess.run(['python3', '/home/debian/verify_safe_memory.py', '--files-only'],
                            capture_output=True, text=True, timeout=120)
    print(result.stdout, end='', flush=True)
    if result.stderr:
        print(result.stderr, end='', flush=True)
    assert result.returncode == 0 and 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS' in result.stdout
    report['file_integrity'] = 'PASS'
    report['temperature_peaks_mC'] = peaks
    report['result'] = 'PASS'
    Path('/home/debian/cpufreq-schedutil-trial.json').write_text(json.dumps(report, indent=2) + '\n')
    os.sync()
    print('CPUFREQ_SCHEDUTIL_BOTH_CLUSTERS_RAM_AND_FILES_PASS', json.dumps(report), flush=True)
finally:
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
    regs.close()
    os.close(fd)
    subprocess.run(['python3', '/home/debian/cleanup_cpufreq_divider.py'], check=True)
