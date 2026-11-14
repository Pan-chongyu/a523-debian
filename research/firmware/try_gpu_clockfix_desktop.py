"""Try accelerated Xorg with a boot-local override and independent rollback."""
import os
from pathlib import Path
import subprocess
import time

assert os.geteuid() == 0 and any(build in os.uname().version for build in ('#3 ', '#4 '))
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/dev/dri/renderD128').exists()
override = Path('/run/systemd/system/lightdm.service.d/95-gpu-clockfix-test.conf')
rollback = Path('/run/tzx-gpu-clockfix-rollback.sh')
rollback.write_text('''#!/bin/sh
set -eu
rm -f /run/systemd/system/lightdm.service.d/95-gpu-clockfix-test.conf
systemctl daemon-reload
systemctl restart lightdm.service
''')
rollback.chmod(0o700)
subprocess.run(['systemd-run','--unit=tzx-gpu-clockfix-rollback','--on-active=15min',
    '/bin/sh',str(rollback)],check=True)
override.parent.mkdir(parents=True,exist_ok=True)
override.write_text('''[Service]
ExecStart=
ExecStart=/usr/sbin/lightdm --config=/usr/local/lib/tzx-accel-gpu/lightdm.conf
''')
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','restart','lightdm.service'],check=True,timeout=25)
environment=dict(os.environ,DISPLAY=':0',XAUTHORITY='/run/lightdm/root/:0')
for attempt in range(25):
    result=subprocess.run(['glxinfo','-B'],env=environment,text=True,capture_output=True,timeout=8)
    if result.returncode==0 and 'Mali-G57' in result.stdout and 'Accelerated: yes' in result.stdout:
        print(result.stdout,flush=True)
        print('CLOCKFIX_DESKTOP_TRIAL_READY_WITH_TIMED_ROLLBACK',flush=True)
        break
    time.sleep(1)
else:
    subprocess.run(['/bin/sh',str(rollback)],check=True,timeout=25)
    raise SystemExit('Clockfix desktop failed; software configuration restored')
