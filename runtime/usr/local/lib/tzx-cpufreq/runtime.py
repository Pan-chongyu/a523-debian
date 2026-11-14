"""Own only the qualified CPU divider module and restore its original clocks."""
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import sys

assert os.geteuid() == 0
assert len(sys.argv) == 2 and sys.argv[1] in ('start', 'stop')
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == Path('/etc/tzx/device-cid').read_text().strip()
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
state_path = Path('/run/tzx-cpufreq-runtime.json')
module = Path('/usr/local/lib/tzx-cpufreq/tzx_cpufreq_divider.ko')
module_sha = '95a0d572d6a363b1b70984cf51e2ae6dff7e8470fc3a2e66072af5a8a508903c'
offsets = (0, 4, 8, 12, 0x60, 0x64, 0x68, 0x6c)

def registers():
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    try:
        with mmap.mmap(fd, 4096, prot=mmap.PROT_READ, offset=0x08817000) as regs:
            return {hex(offset): struct.unpack_from('<I', regs, offset)[0] for offset in offsets}
    finally:
        os.close(fd)

if sys.argv[1] == 'stop':
    if state_path.exists():
        state = json.loads(state_path.read_text())
        assert state['boot_id'] == boot and state['module_sha256'] == module_sha
        if Path('/sys/module/tzx_cpufreq_divider').exists():
            subprocess.run(['rmmod', 'tzx_cpufreq_divider'], check=True, timeout=20)
        assert registers() == state['registers_before']
        assert not list(Path('/sys/devices/system/cpu/cpufreq').glob('policy*'))
        state_path.unlink()
    else:
        assert not Path('/sys/module/tzx_cpufreq_divider').exists()
    print('CPUFREQ_RUNTIME_STOPPED_ORIGINAL_CLOCKS_RESTORED', flush=True)
    raise SystemExit(0)

assert '#5 ' in os.uname().version and os.uname().release == '7.3.3-tzx-a523-accel1'
assert hashlib.sha256(module.read_bytes()).hexdigest() == module_sha
assert not Path('/sys/module/tzx_cpufreq_divider').exists()
assert subprocess.check_output(['systemctl', 'is-active', 'tzx-cpub.service'], text=True).strip() == 'active'
# Early boot may reach this service before any external peripheral module.
# Accept a clean kernel or only the out-of-tree flag; reject every other bit.
taint_before = int(Path('/proc/sys/kernel/tainted').read_text())
assert taint_before in (0, 4096), taint_before
before = registers()
assert not before['0x60'] & (3 << 16) and not before['0x64'] & (3 << 16)
state = {'boot_id': boot, 'module_sha256': module_sha, 'registers_before': before,
         'maximum_kHz': 480000, 'PLL_DSU_voltage_changed': False}
state_path.write_text(json.dumps(state, indent=2) + '\n')
try:
    subprocess.run(['insmod', str(module)], check=True, timeout=20)
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    policies = sorted(Path('/sys/devices/system/cpu/cpufreq').glob('policy*'))
    assert [p.name for p in policies] == ['policy0', 'policy4']
    for index, policy in enumerate(policies):
        assert (policy / 'scaling_driver').read_text().strip() == 'tzx-a523-divider'
        assert (policy / 'related_cpus').read_text().split() == [str(n) for n in range(index*4, index*4+4)]
        assert set((policy / 'scaling_available_frequencies').read_text().split()) == {'120000', '240000', '480000'}
        (policy / 'scaling_max_freq').write_text('480000')
        (policy / 'scaling_min_freq').write_text('120000')
        (policy / 'scaling_governor').write_text('schedutil')
        assert (policy / 'scaling_governor').read_text().strip() == 'schedutil'
    print('CPUFREQ_RUNTIME_TWO_CLUSTERS_SCHEDUTIL_120_240_480_MHZ', json.dumps(state), flush=True)
except BaseException:
    if Path('/sys/module/tzx_cpufreq_divider').exists():
        subprocess.run(['rmmod', 'tzx_cpufreq_divider'], check=True, timeout=20)
    assert registers() == before
    state_path.unlink(missing_ok=True)
    raise
