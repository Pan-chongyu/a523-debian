"""Record first desktop processes without delaying the display manager."""
import json
import os
import subprocess
import time
from pathlib import Path

boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
wanted = {'Xorg', 'xfce4-session', 'xfwm4', 'xfdesktop', 'xfce4-panel'}
hz, until = os.sysconf('SC_CLK_TCK'), time.monotonic()+70
while time.monotonic() < until:
    found = {}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit(): continue
        try:
            name = (path/'comm').read_text().strip()
            if name in wanted:
                found[name] = dict(pid=int(path.name), process_start_kernel_s=
                    int((path/'stat').read_text().split(') ', 1)[1].split()[19])/hz)
        except (FileNotFoundError, ProcessLookupError): pass
    if set(found) == wanted:
        record = dict(boot_id=boot, status='PASS', observed_kernel_s=time.monotonic(),
            desktop_processes=found, last_desktop_process_start_kernel_s=
                max(item['process_start_kernel_s'] for item in found.values()),
            scope='Desktop process start times; not visual readiness or power-button stopwatch')
        for folder in ('/run', '/var/lib/tzx'):
            Path(folder, 'tzx-boot-streamline-desktop.json').write_text(json.dumps(record, indent=2)+'\n')
        print('BOOT_STREAMLINE_DESKTOP_PROCESSES_PRESENT', json.dumps(record), flush=True)
        break
    time.sleep(.15)
else:
    raise RuntimeError('Desktop processes were not ready')
