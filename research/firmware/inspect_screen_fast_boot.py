"""Read the installed boot graph and display/touch timing before optimization."""
import hashlib
import json
from pathlib import Path
import subprocess

def run(*args, timeout=35):
    value = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    return dict(returncode=value.returncode, output=value.stdout)

units = ('tzx-cpub', 'tzx-usb-network', 'tzx-touch', 'tzx-accel-power', 'tzx-display',
         'tzx-gpu', 'tzx-thermal', 'tzx-rtc-context', 'tzx-dram-gpu-health', 'tzx-cpu-cooling',
         'tzx-cpufreq', 'tzx-cpu-dvfs', 'tzx-gpu-performance', 'lightdm', 'tzx-screen-health')
paths = [
    '/usr/local/lib/tzx-peripherals/tzx-touch-runtime-test.sh',
    '/usr/local/lib/tzx-display/tzx-display-runtime',
    '/usr/local/lib/tzx-display/MODULE.sha256',
    '/usr/local/lib/tzx-gpu/tzx-gpu-runtime',
    '/usr/local/lib/tzx-gpu/runtime.py',
]
results = dict(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
               uname=run('uname', '-a'), uptime=Path('/proc/uptime').read_text().strip(),
               commandline=Path('/proc/cmdline').read_text().strip(),
               failed=run('systemctl', '--failed', '--plain', '--no-legend'),
               units={name: run('systemctl', 'cat', name) for name in units},
               properties={name: run('systemctl', 'show', name, '-p', 'After', '-p', 'Before',
                    '-p', 'ActiveEnterTimestampMonotonic', '-p', 'ExecMainStartTimestampMonotonic',
                    '-p', 'Type', '-p', 'ExecStart') for name in units},
               files={str(p): dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                    text=p.read_text()) for p in map(Path, paths) if p.is_file()})
results['kernel'] = run('journalctl', '-b', '-k', '-o', 'short-monotonic', '--no-pager')
results['relevant_journal'] = run('journalctl', '-b', '-o', 'short-monotonic', '--no-pager',
    *[v for name in units for v in ('-u', name)])
print(json.dumps(results, indent=2), flush=True)
