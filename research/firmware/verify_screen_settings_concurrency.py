"""Exercise actual screen commands alongside the running orientation daemon."""
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
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
rotation = json.loads(Path('/home/debian/.config/tzx-screen.json').read_text())['rotation']
command = ['runuser', '-u', 'debian', '--', 'env', *(k+'='+v for k, v in env.items()),
           '/usr/local/bin/tzx-screen', '--rotate', rotation]
results = []
for pair in range(8):
    children = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for _ in range(2)]
    for child in children:
        output = child.communicate(timeout=35)[0]
        result = {'pair': pair, 'returncode': child.returncode, 'output': output}
        results.append(result)
        print(json.dumps(result), flush=True)
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
proof = {'boot_id': boot, 'rotation': rotation, 'commands': results,
         'result': 'PASS' if all(r['returncode'] == 0 for r in results) else 'FAIL'}
Path('/var/lib/tzx/screen-settings-concurrency.json').write_text(json.dumps(proof, indent=2)+'\n')
assert proof['result'] == 'PASS', proof
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
print('TZX_SCREEN_CONCURRENT_SETTINGS_PASS', flush=True)
