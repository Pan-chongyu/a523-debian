"""Configure and open the display utility in the existing local Xfce session."""
import argparse
import json
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('operation', choices=('configure', 'open', 'pattern', 'settings', 'restore'))
a = p.parse_args()
assert os.geteuid() == 0
BACKUP = Path('/root/tzx-recovery/screen-functions-v1/desktop-before.json')
env = None
for proc in Path('/proc').glob('[0-9]*'):
    try:
        if proc.stat().st_uid == 1000 and (proc/'comm').read_text().strip() == 'xfce4-session':
            values = dict(v.split('=', 1) for v in (proc/'environ').read_bytes().decode().split('\0') if '=' in v)
            env = {k: values[k] for k in ('DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR') if k in values}
            break
    except (OSError, ValueError):
        continue
assert env and env.get('DISPLAY') == ':0'
prefix = ['runuser', '-u', 'debian', '--', 'env', *(k+'='+v for k, v in env.items())]


def user(*cmd, check=True):
    return subprocess.run([*prefix, *cmd], text=True, capture_output=True, timeout=20, check=check)


properties = {
    '/xfce4-power-manager/presentation-mode': ('bool', 'false'),
    '/xfce4-power-manager/dpms-enabled': ('bool', 'true'),
    '/xfce4-power-manager/dpms-on-ac-sleep': ('uint', '0'),
    '/xfce4-power-manager/dpms-on-ac-off': ('uint', '10'),
    '/xfce4-power-manager/dpms-on-battery-sleep': ('uint', '0'),
    '/xfce4-power-manager/dpms-on-battery-off': ('uint', '5'),
}
if a.operation == 'configure':
    before = {}
    assert not BACKUP.exists()
    for name, (kind, value) in properties.items():
        result = user('xfconf-query', '-c', 'xfce4-power-manager', '-p', name, check=False)
        before[name] = {'type': kind, 'value': result.stdout.strip() if result.returncode == 0 else None}
    with BACKUP.open('x') as f:
        json.dump(before, f, indent=2)
        f.write('\n')
        os.fchmod(f.fileno(), 0o600)
        f.flush()
        os.fsync(f.fileno())
    for name, (kind, value) in properties.items():
        if before[name]['value'] is None:
            user('xfconf-query', '-c', 'xfce4-power-manager', '-p', name, '-n', '-t', kind, '-s', value)
        else:
            user('xfconf-query', '-c', 'xfce4-power-manager', '-p', name, '-s', value)
        assert user('xfconf-query', '-c', 'xfce4-power-manager', '-p', name).stdout.strip() == value
    desktop = Path(user('xdg-user-dir', 'DESKTOP').stdout.strip())
    assert desktop.parent == Path('/home/debian')
    shortcut = desktop/'屏幕设置.desktop'
    assert not shortcut.exists()
    shortcut.write_bytes(Path('/usr/share/applications/tzx-screen.desktop').read_bytes())
    shortcut.chmod(0o755)
    os.chown(shortcut, 1000, 1000)
    print('SCREEN_DESKTOP_DPMS_CONFIGURED', desktop, flush=True)
elif a.operation == 'restore':
    before = json.loads(BACKUP.read_text())
    for name, item in before.items():
        if item['value'] is None:
            user('xfconf-query', '-c', 'xfce4-power-manager', '-p', name, '-r', check=False)
        else:
            user('xfconf-query', '-c', 'xfce4-power-manager', '-p', name, '-s', item['value'])
    desktop = Path(user('xdg-user-dir', 'DESKTOP').stdout.strip())
    shortcut = desktop/'屏幕设置.desktop'
    original = Path('/usr/share/applications/tzx-screen.desktop')
    if shortcut.is_file() and original.is_file() and shortcut.read_bytes() == original.read_bytes():
        shortcut.unlink()
    print('SCREEN_DESKTOP_DPMS_SETTINGS_RESTORED', flush=True)
elif a.operation == 'settings':
    for name in properties:
        print(name, user('xfconf-query', '-c', 'xfce4-power-manager', '-p', name).stdout.strip())
    print(user('xset', 'q').stdout)
else:
    unit = 'tzx-screen-settings' if a.operation == 'open' else 'tzx-screen-pattern'
    command = ['systemd-run', '--unit='+unit, '--uid=debian', '--collect', '--service-type=exec',
               *('--setenv='+k+'='+v for k, v in env.items()), '/usr/local/bin/tzx-screen']
    if a.operation == 'pattern':
        command.append('--show-pattern')
    subprocess.run(command, check=True, timeout=20)
