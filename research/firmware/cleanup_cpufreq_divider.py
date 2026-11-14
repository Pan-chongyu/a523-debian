"""Unload the manual CPU divider module and confirm its exact restoration."""
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
if Path('/sys/module/tzx_cpufreq_divider').exists():
    subprocess.run(['rmmod', 'tzx_cpufreq_divider'], check=True, timeout=30)
before_path = Path('/run/tzx-cpufreq-before.json')
if before_path.exists():
    before = json.loads(before_path.read_text())
    assert before['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    with mmap.mmap(fd, 4096, prot=mmap.PROT_READ, offset=0x08817000) as regs:
        actual = {name: struct.unpack_from('<I', regs, int(name, 16))[0]
                  for name in before['registers']}
    os.close(fd)
    assert actual == before['registers'], (actual, before['registers'])
assert not list(Path('/sys/devices/system/cpu/cpufreq').glob('policy*'))
subprocess.run(['systemctl', 'stop', 'tzx-cpufreq-independent-rollback.timer'], check=False, timeout=15)
print('CPUFREQ_DIVIDER_UNLOADED_EXACT_BASELINE_RESTORED', flush=True)
