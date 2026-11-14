"""Install the graphics kernel's read-only battery module on the exact tablet."""
from pathlib import Path
import hashlib
import shlex
import subprocess

root = Path(__file__).resolve().parents[1]
helper = root / 'tools/tablet_ssh.py'
module = root / 'build/battery-graphics/tzx_battery.ko'
digest = hashlib.sha256(module.read_bytes()).hexdigest()
subprocess.run(['py', '-3.11', '-X', 'utf8', str(helper), '--file', str(module), '--remote', '/home/debian/tzx_battery-gfx1.ko'], check=True)
subprocess.run(['py', '-3.11', '-X', 'utf8', str(helper), '--file', str(root/'firmware/tzx-battery.service'), '--remote', '/home/debian/tzx-battery.service'], check=True)
command = '''set -eu
test "$(cat /sys/class/block/mmcblk0/device/cid)" = 3e01ff55454d20202010209170281b59
printf '%s\\n' ''' + shlex.quote(digest + '  /home/debian/tzx_battery-gfx1.ko') + ''' | sha256sum -c -
install -m 644 /home/debian/tzx_battery-gfx1.ko /lib/modules/7.3.3-tzx-a523-gfx1/extra/tzx_battery.ko
install -m 644 /home/debian/tzx-battery.service /etc/systemd/system/tzx-battery.service
depmod -a 7.3.3-tzx-a523-gfx1
systemctl daemon-reload
systemctl enable tzx-battery.service
sync
'''
subprocess.run(['py', '-3.11', '-X', 'utf8', str(helper), '--root', '--command', command, '--output', 'battery-gfx1-installed.txt'], check=True)
