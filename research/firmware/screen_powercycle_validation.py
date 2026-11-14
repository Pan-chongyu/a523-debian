"""Record a qualified display power-off test and check the subsequent key-on boot."""
import argparse
import json
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('operation', choices=('poweroff', 'verify'))
a = p.parse_args()
assert os.geteuid() == 0
root = Path('/var/lib/tzx')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
intent_path = root/'screen-powercycle-intent.json'


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=55)


def record(path, data):
    temp = path.with_suffix('.new')
    with temp.open('w') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


if a.operation == 'poweroff':
    assert not intent_path.exists()
    state = json.loads((root/'screen-installed.json').read_text())
    assert state['verified_boot_id'] == boot and state['profile'] == 'screen-functions-5-poweron'
    proof = json.loads((root/'screen-poweron-test.json').read_text())
    assert proof['boot_id'] == boot and proof['result'] == 'PASS' and proof['kernel_console_rotation_enabled']
    assert Path('/sys/module/tzx_pmic_poweroff/parameters/armed').read_text().strip() in ('1', 'Y')
    assert not run('systemctl', '--failed', '--no-legend').strip()
    props = run('systemctl', 'show', 'tzx-screen-poweron-postboot-checks', '-p', 'ActiveState', '-p', 'Result', '-p', 'ExecMainStatus')
    assert all(v in props for v in ('ActiveState=inactive', 'Result=success', 'ExecMainStatus=0'))
    journal = run('journalctl', '-b', '-u', 'tzx-screen-poweron-postboot-checks', '-o', 'cat', '--no-pager')
    assert 'GPU_FULL_X11_WITH_1_SCENES_AND_THREE_512MIB_CPU_MEMORY_PASSES' in journal
    intent = {'previous_boot_id': boot, 'brightness': int(Path('/sys/class/backlight/tzx-panel/brightness').read_text()),
              'orientation': 'right', 'screen_profile': state['profile'], 'poweroff': 'PMIC handler armed',
              'scope': 'normal software poweroff, USB kept connected, physical key-on; not battery-disconnected power cycle'}
    record(intent_path, intent)
    record(root/'screen-reboot-intent.json', intent)
    os.sync()
    print(run('systemd-run', '--unit=tzx-screen-powercycle-off', '--on-active=5s', '/usr/bin/systemctl', 'poweroff'), flush=True)
    print('SCREEN_POWERCYCLE_POWER_OFF_SCHEDULED', json.dumps(intent), flush=True)
else:
    intent = json.loads(intent_path.read_text())
    assert boot != intent['previous_boot_id']
    for command in (('python3', '/home/debian/install_screen_boot_kernel.py', 'verify-boot'),
                    ('python3', '/home/debian/verify_screen_poweron.py', '--after-boot'),
                    ('python3', '/home/debian/verify_screen_boot.py')):
        print(run(*command), flush=True)
    proof = json.loads((root/'screen-poweron-test.json').read_text())
    assert proof['boot_id'] == boot and proof['result'] == 'PASS'
    result = {'boot_id': boot, 'result': 'PASS', 'intent': intent, 'poweron_proof': proof,
              'scope': intent['scope'], 'user_observed_poweroff_and_key_on': 'awaiting_user_confirmation'}
    record(root/'screen-powercycle-test.json', result)
    print('SCREEN_PMIC_OFF_KEY_ON_NEW_BOOT_AND_DISPLAY_PASS', json.dumps(result), flush=True)
