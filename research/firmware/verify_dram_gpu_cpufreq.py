"""Bounded coexistence qualification: trained DRAM, GPU and divider schedutil."""
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import time

ROOT = Path('/home/debian')
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert os.geteuid() == 0
assert '#5 ' in os.uname().version
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert json.loads(Path('/var/lib/tzx/dram-gpu-boot-health.json').read_text())['boot_id'] == BOOT
assert not Path('/var/lib/tzx/dram-gpu-boot-pending.json').exists()
subprocess.run(['python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard'], check=True, timeout=30)
assert subprocess.check_output(['systemctl', 'is-active', 'tzx-cpufreq.service'], text=True).strip() == 'active'
assert Path('/sys/module/panfrost/parameters/tzx_dma32').read_text().strip() == 'Y'
work = ROOT/'cpufreq-divider-trial/cpu-frequency-workload'
copy = ROOT/'library-copy-coherency-v8'
assert hashlib.sha256(work.read_bytes()).hexdigest() == '78ad0fd992c8bd9229a5ff7adf59c4d9eb5fff47d8a79e11644e32300985a7df'
assert hashlib.sha256(copy.read_bytes()).hexdigest() == '342d0c7e9bb52e84bfda236629d08382ea350c2abb35e4c2e7a320204e5ee517'
assert hashlib.sha256(Path('/usr/local/lib/tzx-cpufreq/tzx_cpufreq_divider.ko').read_bytes()).hexdigest() == '95a0d572d6a363b1b70984cf51e2ae6dff7e8470fc3a2e66072af5a8a508903c'
policies = [Path('/sys/devices/system/cpu/cpufreq')/f'policy{cpu}' for cpu in (0, 4)]
for policy in policies:
    for name, value in (('scaling_driver', 'tzx-a523-divider'), ('scaling_governor', 'schedutil'),
                        ('scaling_min_freq', '120000'), ('scaling_max_freq', '480000')):
        assert (policy/name).read_text().strip() == value, (policy, name)
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
regs = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x08817000)
offsets = (0, 4, 8, 12, 0x60, 0x64, 0x68, 0x6c)
initial = {offset: struct.unpack_from('<I', regs, offset)[0] for offset in offsets}
children = []
peaks = {}
samples = []
started = time.monotonic()


def sample():
    assert time.monotonic()-started < 550
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    freqs = []
    for offset, before in initial.items():
        now = struct.unpack_from('<I', regs, offset)[0]
        if offset in (0x60, 0x64):
            assert now & ~(3 << 16) == before & ~(3 << 16)
            divider = (now >> 16) & 3
            assert divider in (0, 1, 2)
            freqs.append(480000 >> divider)
        else:
            assert now == before, (hex(offset), hex(before), hex(now))
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        temp = int((zone/'temp').read_text())
        assert 0 < temp < 75000
        name = (zone/'type').read_text().strip()
        peaks[name] = max(peaks.get(name, 0), temp)
    samples.append(freqs)
    return freqs


def wait(process, timeout):
    limit = time.monotonic()+timeout
    while process.poll() is None:
        sample()
        assert time.monotonic() < limit, 'Child workload deadline'
        time.sleep(0.2)
    assert process.returncode == 0, process.returncode


def idle():
    rows = []
    limit = time.monotonic()+7
    while time.monotonic() < limit:
        rows.append(sample())
        time.sleep(0.2)
    minimum = [min(row[i] for row in rows) for i in range(2)]
    assert all(v < 480000 for v in minimum), minimum
    return minimum


def spawn(command, **kwargs):
    process = subprocess.Popen(command, **kwargs)
    children.append(process)
    return process


report = {'boot_id': BOOT, 'maximum_cpu_kHz': 480000, 'gpu': 'Mali-G57 DMA32 AArch64',
          'full_4GiB': True, 'PLL_DSU_voltage_changed': False}
try:
    env = dict(os.environ, TZX_GPU_EXPECT_AWAKE='0', TZX_GPU_TRACE_SCENES='1')
    process = spawn(['python3', '-u', str(ROOT/'verify_gpu_memory_pressure.py'), '--memory-mib',
                     '2560', '--gpu-cycles', '2', '--backend', 'x11',
                     '--log-prefix', 'gpu-dram1260-cpufreq-auto'], env=env)
    wait(process, 300)
    report['GPU_two_full_suites_and_three_2560MiB_checks'] = 'PASS'
    report['idle_before_minimum_kHz'] = idle()
    busy = []
    for repeat in range(5):
        workers = [spawn([str(work), str(cpu)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True) for cpu in range(8)]
        while any(p.poll() is None for p in workers):
            busy.append(sample())
            time.sleep(0.1)
        for worker in workers:
            output = worker.communicate(timeout=5)[0]
            assert worker.returncode == 0 and json.loads(output)['checksum'] == 'a56490781b5a25dd', output
    high = [max(row[i] for row in busy) for i in range(2)]
    assert high == [480000, 480000], high
    report['load_maximum_kHz'] = high
    report['workload_checksums_40'] = 'PASS'
    report['idle_after_minimum_kHz'] = idle()
    print('DRAM_GPU_CPUFREQ_IDLE_LOAD_IDLE_CHECKSUMS_PASS', json.dumps(report), flush=True)
    prefix = ROOT/'copy-dram1260-cpufreq-gpu-v8'
    assert not list(ROOT.glob(prefix.name+'-*'))
    env['TZX_COPY_HIGH_TARGETS'] = '1'
    process = spawn([str(copy), '120', str(prefix), '255', 'libc'], env=env)
    wait(process, 175)
    report['ordinary_libc_copy_high_addresses_120_seconds'] = 'PASS'
    process = spawn(['python3', '-u', str(ROOT/'verify_safe_memory.py'), '--files-only'])
    wait(process, 120)
    report['file_cache_direct_and_package_audit'] = 'PASS'
    subprocess.run(['python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard'], check=True, timeout=30)
    report.update(result='PASS', elapsed_seconds=round(time.monotonic()-started, 2),
                  temperature_peaks_mC=peaks, samples=len(samples),
                  registers_before={hex(k): hex(v) for k, v in initial.items()})
    target = Path('/var/lib/tzx/dram-gpu-cpufreq-coexistence.json')
    temporary = target.with_suffix('.new')
    with temporary.open('w') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fchmod(stream.fileno(), 0o600)
        os.fsync(stream.fileno())
    temporary.replace(target)
    directory = os.open(target.parent, os.O_DIRECTORY)
    os.fsync(directory)
    os.close(directory)
    print('DRAM_GPU_CPUFREQ_COEXISTENCE_QUALIFICATION_PASS', json.dumps(report), flush=True)
finally:
    for process in children:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    regs.close()
    os.close(fd)
