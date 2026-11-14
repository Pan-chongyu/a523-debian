"""Read the real startup inputs, timings and desktop processes for one boot."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

assert os.geteuid() == 0
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
names = ('tzx-cpub', 'tzx-boot-panel-handoff', 'tzx-touch', 'tzx-touch-input-ready',
         'tzx-thermal', 'tzx-early-performance-check', 'tzx-cpu-dvfs', 'tzx-display',
         'tzx-gpu', 'lightdm', 'tzx-screen-health', 'tzx-emmc-hs', 'tzx-wifi', 'tzx-bluetooth')
paths = ('/usr/local/lib/tzx-boot-panel/handoff.py',
         '/usr/local/lib/tzx-gpu-devfreq/startup.py',
         '/usr/local/lib/tzx-emmc-hs/runtime.py',
         '/usr/local/lib/tzx-emmc-hs/manifest.json',
         '/usr/local/lib/tzx-performance-mode/manifest.json',
         '/usr/local/lib/tzx-accel-bluetooth/runtime.py',
         '/etc/systemd/system/tzx-early-performance-check.service',
         '/etc/systemd/system/tzx-emmc-hs.service',
         '/etc/systemd/system/tzx-bluetooth.service')
files = {name: dict(text=Path(name).read_text(), sha256=hashlib.sha256(Path(name).read_bytes()).hexdigest(),
                    mode=Path(name).stat().st_mode & 0o777) for name in paths}
units = {}
for name in names:
    output = subprocess.check_output(['systemctl', 'show', name, '-p', 'After', '-p', 'Before',
        '-p', 'ExecMainStartTimestampMonotonic', '-p', 'ActiveEnterTimestampMonotonic',
        '-p', 'ActiveState', '-p', 'Requires', '-p', 'MainPID'], text=True, timeout=10)
    units[name] = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
desktop, hz = [], os.sysconf('SC_CLK_TCK')
for path in Path('/proc').iterdir():
    if not path.name.isdigit(): continue
    try:
        name = (path/'comm').read_text().strip()
        if name in ('Xorg', 'xfce4-session', 'xfwm4', 'xfdesktop', 'xfce4-panel'):
            desktop.append(dict(name=name, pid=int(path.name),
                process_start_kernel_s=int((path/'stat').read_text().split(') ', 1)[1].split()[19])/hz))
    except (FileNotFoundError, ProcessLookupError): pass
states = {}
for name in ('boot-logo-stage', 'boot-panel-stage', 'screen-boot-health'):
    states[name] = json.loads(Path('/var/lib/tzx', name+'.json').read_text())
link = Path('/etc/systemd/system/multi-user.target.wants/tzx-bluetooth.service')
record = dict(boot_id=boot, files=files, units=units, desktop_processes=desktop,
    state=states, bluetooth_boot_link=os.readlink(link) if link.is_symlink() else None,
    systemd_time=subprocess.check_output(['systemd-analyze', 'time'], text=True),
    kernel_image_sha256=hashlib.sha256(Path('/boot/Image').read_bytes()).hexdigest())
assert boot == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
print(json.dumps(record, indent=2))
