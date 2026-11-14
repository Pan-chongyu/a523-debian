"""Repair omissions found in the actual initial XFCE boot."""
from pathlib import Path
import os
import subprocess

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
release = os.uname().release
override = Path('/etc/systemd/system/upower.service.d/10-tzx-bootstrap.conf')
if release == '7.3.3-tzx-a523-gfx1':
    # gfx1 lacks USER_NS. Remove this override once the next kernel is live.
    override.parent.mkdir(exist_ok=True, parents=True)
    override.write_text('[Service]\nPrivateUsers=no\n')
elif release == '7.3.3-tzx-a523-periph1':
    override.unlink(missing_ok=True)
else:
    raise SystemExit('Unverified kernel')
Path('/var/lib/lightdm/data').mkdir(exist_ok=True, parents=True)
Path('/run/utmp').touch(exist_ok=True)
os.chmod('/run/utmp', 0o664)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemctl', 'reset-failed', 'upower'], check=True)
subprocess.run(['systemctl', 'restart', 'upower'], check=True)
subprocess.run(['upower', '-d'], check=True)
