"""Try the GPU Xorg configuration with an independent timed rollback."""
from pathlib import Path
import json
import os
import subprocess
import time

assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1'
assert Path('/dev/dri/renderD128').exists()
target = Path('/etc/X11/xorg.conf.d/20-tzx-display.conf')
backup = Path('/root/tzx-recovery/periph1/20-tzx-display.conf')
backup.parent.mkdir(parents=True, exist_ok=True)
if not backup.exists():
    backup.write_bytes(target.read_bytes())
candidate = Path('/home/debian/30-tzx-acceleration.conf')
rollback = Path('/root/tzx-recovery/rollback-xorg.sh')
rollback.write_text('''#!/bin/sh
set -eu
cp /root/tzx-recovery/periph1/20-tzx-display.conf /etc/X11/xorg.conf.d/20-tzx-display.conf
systemctl restart lightdm
''')
rollback.chmod(0o700)
unit = 'tzx-xorg-rollback-' + str(os.getpid())
subprocess.run(['systemd-run', '--unit', unit, '--on-active=90s', '/bin/sh', str(rollback)], check=True)
target.write_bytes(candidate.read_bytes())
subprocess.run(['systemctl', 'restart', 'lightdm'], check=True, timeout=25)
environment = dict(os.environ, DISPLAY=':0', XAUTHORITY='/run/lightdm/root/:0')
output = ''
for attempt in range(20):
    check = subprocess.run(['glxinfo', '-B'], env=environment, capture_output=True, text=True, timeout=8)
    output = check.stdout + check.stderr
    if check.returncode == 0 and 'Mali-G57' in output and 'Accelerated: yes' in output:
        subprocess.run(['systemctl', 'stop', unit+'.timer'], check=True)
        print(output, flush=True)
        print(json.dumps({'desktop_gl_accelerated': True, 'rollback_timer_cancelled': True}), flush=True)
        break
    time.sleep(1)
else:
    print(output, flush=True)
    for name in ['/var/log/Xorg.0.log', '/var/log/lightdm/lightdm.log']:
        path = Path(name)
        if path.exists():
            (Path('/home/debian')/('gpu-trial-'+path.name)).write_bytes(path.read_bytes())
    subprocess.run(['/bin/sh', str(rollback)], check=True, timeout=25)
    subprocess.run(['systemctl', 'stop', unit+'.timer'], check=True)
    raise SystemExit('GPU_DESKTOP_FAILED_SOFTWARE_CONFIGURATION_RESTORED')
