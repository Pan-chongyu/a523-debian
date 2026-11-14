"""Collect actual post-reboot graphics state without changing the tablet."""
from pathlib import Path
import hashlib
import json
import os
import subprocess

assert os.geteuid() == 0
def read(name):
    path = Path(name)
    return path.read_text(errors='replace').strip() if path.exists() else None
def command(args):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return {'returncode': result.returncode, 'output': result.stdout.decode(errors='replace')}
assert read('/sys/class/block/mmcblk0/device/cid') == '3e01ff55454d20202010209170281b59'
release = os.uname().release
report = {
    'release': release, 'boot_id': read('/proc/sys/kernel/random/boot_id'),
    'uptime': read('/proc/uptime'),
    'services': {}, 'drm': {}, 'backlight': {}, 'power': {},
    'devices': {name: Path(name).exists() for name in ['/dev/dri/card0', '/dev/fb0', '/dev/ttyGS0']},
}
for name in ['tzx-touch', 'tzx-wifi', 'tzx-display', 'tzx-battery', 'lightdm', 'NetworkManager']:
    report['services'][name] = command(['systemctl', 'show', name, '-p', 'ActiveState', '-p', 'SubState', '-p', 'Result'])
for path in Path('/sys/class/drm').glob('card*-*'):
    report['drm'][path.name] = {key: read(path/key) for key in ['status', 'enabled', 'modes']}
for path in Path('/sys/class/backlight').glob('*'):
    report['backlight'][path.name] = {key: read(path/key) for key in ['brightness', 'actual_brightness', 'max_brightness', 'bl_power']}
for path in Path('/sys/class/power_supply').glob('*'):
    report['power'][path.name] = read(path/'uevent')
report['de_report'] = read('/sys/module/tzx_display/parameters/de_report')
report['framebuffer'] = read('/proc/fb')
report['failed_units'] = command(['systemctl', '--failed', '--no-pager'])
report['display_log'] = command(['journalctl', '-u', 'tzx-display', '-u', 'lightdm', '-b', '-n', '65', '--no-pager'])
report['kernel_log'] = command(['dmesg', '--level=err,warn'])
report['network'] = command(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE', 'device'])
print(json.dumps(report, ensure_ascii=False, indent=2))
