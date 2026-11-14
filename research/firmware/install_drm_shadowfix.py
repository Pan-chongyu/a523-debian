"""Switch only the accel1 display module; retain an exact local rollback."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--restore', action='store_true')
parser.add_argument('--primefix', action='store_true')
args = parser.parse_args()
assert not (args.restore and args.primefix)
assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#3 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
old_sha = 'a35bf0f313a1ac2131c39cf59a9554636397d14d09836e2c2e4d445396d32b4a'
new_sha = '4f9325e0a216e09c598cb6ce3a613197aa8bd7105ce97a263a631447ca37a03a'
prime_sha = 'a00991fbcf52fd9624fb62b708e108ad22edf30546c84d3a5bffa65cc7a2a27f'
module = Path('/lib/modules/7.3.3-tzx-a523-accel1/extra/tzx_display.ko')
guard = Path('/usr/local/lib/tzx-accel-display/MODULE.sha256')
backup = Path('/root/tzx-recovery/drm-before-shadowfix')
backup.mkdir(parents=True, exist_ok=True)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def run(*command, timeout=40):
    return subprocess.run(command, check=True, timeout=timeout)

def atomic_write(path, data):
    tmp = path.with_name(path.name + '.shadowfix-tmp')
    with tmp.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.chmod(0o644)
    tmp.replace(path)

current = module.read_bytes()
assert digest(current) in (old_sha, new_sha, prime_sha)
if not (backup/'tzx_display.ko').exists():
    assert digest(current) == old_sha
    atomic_write(backup/'tzx_display.ko', current)
    atomic_write(backup/'MODULE.sha256', guard.read_bytes())
assert digest((backup/'tzx_display.ko').read_bytes()) == old_sha
candidate = '/home/debian/tzx_display-primefix.ko' if args.primefix else '/home/debian/tzx_display-shadowfix.ko'
target = (backup/'tzx_display.ko').read_bytes() if args.restore else Path(candidate).read_bytes()
expected = old_sha if args.restore else prime_sha if args.primefix else new_sha
assert digest(target) == expected
assert not Path('/var/lib/tzx/gpu-qualified').exists()
assert not Path('/run/systemd/system/lightdm.service.d/95-gpu-clockfix-test.conf').exists()
assert not int(Path('/proc/sys/kernel/tainted').read_text()) & 128

run('systemctl', 'stop', 'lightdm.service')
try:
    # No live GPU contexts or display clients may survive the switch.
    if Path('/sys/module/panfrost').exists():
        run('modprobe', '-r', 'panfrost')
    run('systemctl', 'stop', 'tzx-display.service')
    assert not Path('/sys/module/tzx_display').exists()
    atomic_write(module, target)
    atomic_write(guard, (expected + '  ' + str(module) + '\n').encode())
    run('depmod', '-a', os.uname().release)
    run('systemctl', 'start', 'tzx-display.service')
    run('systemctl', 'start', 'lightdm.service')
    environment = dict(os.environ, DISPLAY=':0', XAUTHORITY='/run/lightdm/root/:0')
    for attempt in range(25):
        result = subprocess.run(['glxinfo', '-B'], env=environment, text=True,
                                capture_output=True, timeout=8)
        if result.returncode == 0 and 'llvmpipe' in result.stdout:
            print(result.stdout, flush=True)
            break
        time.sleep(1)
    else:
        raise RuntimeError('Software desktop did not return')
except BaseException:
    run('systemctl', 'stop', 'lightdm.service')
    run('systemctl', 'stop', 'tzx-display.service')
    assert not Path('/sys/module/tzx_display').exists()
    atomic_write(module, (backup/'tzx_display.ko').read_bytes())
    atomic_write(guard, (backup/'MODULE.sha256').read_bytes())
    run('depmod', '-a', os.uname().release)
    run('systemctl', 'reset-failed', 'tzx-display.service')
    run('systemctl', 'start', 'tzx-display.service')
    run('systemctl', 'start', 'lightdm.service')
    raise
assert digest(module.read_bytes()) == expected
print('DISPLAY_SWITCH_PASS', expected, flush=True)
run('sync')
