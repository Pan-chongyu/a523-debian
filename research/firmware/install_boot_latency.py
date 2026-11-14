"""Shorten this board's boot without changing clocks, rails or boot sectors."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

assert os.geteuid() == 0
assert sys.argv[1:] in (['install'], ['restore'])
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
BACKUP = Path('/root/tzx-recovery/boot-latency-v1')
STATE = Path('/var/lib/tzx/boot-latency-installed.json')
sha = lambda b: hashlib.sha256(b).hexdigest()
PINS = {
    '/etc/systemd/system/tzx-cpub.service': '1d842e8e7c4b929e69d5c37271c9e22b5117667d369741803252098086745c84',
    '/etc/systemd/system/tzx-display.service': '88e00003897bf7a41b458683c3ed891e67257ecd11e3474ea2b4f20bc147c629',
}


def run(*args, timeout=60):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=timeout)


def atomic(path, data, mode=0o644):
    assert not path.is_symlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.boot-latency-new')
    with temp.open('wb') as f:
        f.write(data)
        os.fchmod(f.fileno(), mode)
        f.flush()
        os.fsync(f.fileno())
    temp.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)


def record(path, value):
    atomic(path, (json.dumps(value, indent=2) + '\n').encode(), 0o600)


def properties(unit):
    output = run('systemctl', 'show', unit, '-p', 'Id', '-p', 'After', '-p', 'Before',
                 '-p', 'DefaultDependencies', '-p', 'ActiveEnterTimestampMonotonic',
                 '-p', 'ExecMainStartTimestampMonotonic')
    return dict(line.split('=', 1) for line in output.splitlines() if '=' in line)


if sys.argv[1] == 'restore':
    state = json.loads(STATE.read_text())
    for name, item in state['files'].items():
        path = Path(name)
        assert sha(path.read_bytes()) == item['installed_sha256'], name
    for name, item in state['files'].items():
        original = (BACKUP / 'files' / name.lstrip('/')).read_bytes()
        assert sha(original) == PINS[name]
        atomic(Path(name), original, item['mode'])
    run('systemctl', 'daemon-reload')
    state.update(state='original-order-restored', restored_boot_id=BOOT)
    record(STATE, state)
    print('BOOT_LATENCY_ORIGINAL_ORDER_RESTORED', flush=True)
    raise SystemExit(0)

assert not BACKUP.exists() and not STATE.exists()
assert sha(Path('/usr/local/sbin/tzx-enable-cpub').read_bytes()) == '4f23b812c70b7fe2f58543b70368cf7ae646e8bf12a577c0f7fe7f90c83a5d77'
assert not run('systemctl', '--failed', '--plain', '--no-legend').strip()
assert run('systemctl', 'is-active', 'tzx-display', 'tzx-touch', 'tzx-cpub',
           'tzx-cpu-dvfs', 'tzx-gpu-performance', 'lightdm').split() == ['active'] * 6
old = {name: Path(name).read_bytes() for name in PINS}
for name, data in old.items():
    assert sha(data) == PINS[name], name
assert Path('/etc/fstab').read_text().splitlines()[0] == 'LABEL=DEBIAN_ROOT / ext4 defaults,noatime 0 1'

new = {}
name = '/etc/systemd/system/tzx-cpub.service'
text = old[name].decode()
assert text.count('After=local-fs.target\n') == 1
assert text.count('Before=multi-user.target\n') == 1
text = text.replace('After=local-fs.target\n',
    'DefaultDependencies=no\nAfter=systemd-remount-fs.service\nConflicts=shutdown.target\n')
text = text.replace('Before=multi-user.target\n',
    'Before=multi-user.target shutdown.target systemd-udevd.service systemd-udev-trigger.service\n')
text = text.replace('Type=oneshot\n', 'Type=oneshot\nTimeoutStartSec=5s\n')
new[name] = text.encode()
name = '/etc/systemd/system/tzx-display.service'
text = old[name].decode()
assert text.count('After=tzx-touch.service tzx-wifi.service\n') == 1
new[name] = text.replace('After=tzx-touch.service tzx-wifi.service\n',
    'After=tzx-touch.service\n').encode()

before = {unit: properties(unit) for unit in ('tzx-cpub', 'tzx-touch', 'tzx-display',
    'tzx-wifi', 'tzx-gpu', 'lightdm', 'graphical.target')}
BACKUP.mkdir(parents=True)
files = {}
for name, data in old.items():
    mode = Path(name).stat().st_mode & 0o777
    atomic(BACKUP / 'files' / name.lstrip('/'), data, mode)
    files[name] = dict(original_sha256=PINS[name], installed_sha256=sha(new[name]), mode=mode)
atomic(BACKUP / 'install_boot_latency.py', Path(__file__).read_bytes(), 0o600)
record(BACKUP / 'before.json', dict(boot_id=BOOT, files=files, units=before,
    time=run('systemd-analyze', 'time'), critical_chain=run('systemd-analyze', 'critical-chain')))

try:
    for name, data in new.items():
        atomic(Path(name), data, files[name]['mode'])
    verification = run('systemd-analyze', 'verify', '--man=no',
                       'tzx-cpub.service', 'tzx-display.service', 'graphical.target')
    assert 'cycle' not in verification.lower(), verification
    run('systemctl', 'daemon-reload')
    cpub = properties('tzx-cpub.service')
    display = properties('tzx-display.service')
    assert cpub['DefaultDependencies'] == 'no'
    assert 'systemd-remount-fs.service' in cpub['After'].split()
    assert not set(cpub['After'].split()) & {'basic.target', 'sysinit.target', 'local-fs.target'}
    assert {'systemd-udevd.service', 'systemd-udev-trigger.service', 'shutdown.target'} <= set(cpub['Before'].split())
    assert 'tzx-wifi.service' not in display['After'].split()
    assert {'tzx-touch.service', 'tzx-accel-power.service'} <= set(display['After'].split())
    record(STATE, dict(state='installed-pending-normal-reboot', installed_boot_id=BOOT,
        requested_unix=int(time.time()), files=files, backup=str(BACKUP),
        verification=verification, effective_cpub=cpub, effective_display=display,
        baseline_units=before, cpu_clock_binary_unchanged=True, raw_boot_areas_changed=False,
        display_touch_rail_order_preserved=True, existing_dropins_preserved=True))
    os.sync()
except BaseException:
    for name, data in old.items():
        atomic(Path(name), data, files[name]['mode'])
    run('systemctl', 'daemon-reload')
    raise

print('BOOT_LATENCY_V1_INSTALLED_PENDING_REBOOT', json.dumps(dict(files=files,
      cpub=cpub, display=display)), flush=True)
