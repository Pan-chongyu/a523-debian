"""Read-only boot timing and retained hardware receipts."""
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess

def run(*args):
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=40)
    print('COMMAND', list(args), 'RETURN', p.returncode, flush=True)
    print(p.stdout, flush=True)

fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
try:
    def words(addr, count):
        base = addr & ~4095
        with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=base) as mem:
            return [hex(v) for v in struct.unpack_from('<'+'I'*count, mem, addr-base)]
    print('EARLY_CPUB', words(0x2df40, 6), flush=True)
    print('BOOT_WIDE', words(0x2df80, 8), flush=True)
    print('PLL_CPUS', words(0x8817000, 6), flush=True)
    print('MUX_CPUS', words(0x8817060, 2), flush=True)
finally:
    os.close(fd)
for name in ('cpu-dvfs', 'gpu-performance', 'emmc-hs'):
    print('RUNTIME', name, Path('/run/tzx-'+name+'.json').read_text(), flush=True)
run('systemd-analyze', 'time')
run('systemd-analyze', 'critical-chain', 'tzx-display.service')
run('systemd-analyze', 'blame')
run('journalctl', '-b', '-o', 'short-monotonic', '--no-pager', '-u', 'tzx-display', '-u', 'tzx-cpub', '-u', 'systemd-udevd', '-u', 'tzx-touch', '-u', 'lightdm')
run('journalctl', '-b', '-1', '-o', 'short-monotonic', '--no-pager', '-n', '100')
run('dmesg')
