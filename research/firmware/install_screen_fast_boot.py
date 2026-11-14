"""Allow display after touch rails settle, while retaining full input before login."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

assert os.geteuid() == 0 and sys.argv[1:] in (['install'], ['verify'], ['restore'])
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
state = Path('/var/lib/tzx/screen-fast-installed.json')
backup = Path('/root/tzx-recovery/screen-fast-rail-v1')
sha = lambda b: hashlib.sha256(b).hexdigest()
touch_unit = '/etc/systemd/system/tzx-touch.service'
touch_script = '/usr/local/lib/tzx-peripherals-accel1/tzx-touch-runtime-test.sh'
helper = '/usr/local/lib/tzx-screen-fast/touch_ready.py'
pins = {touch_unit: 'e0219af94a890da2fd0b998ed701efc476da8089bb765d3fb12abd7cc4f20f25',
        touch_script: 'a56530d38a5eab65e751c9f243c153aa116a73f98b04207e9e0db43ce35868e9'}

def run(*args, timeout=30):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=timeout)

def atomic(path, data, mode=0o644):
    path = Path(path)
    assert not path.is_symlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.screen-fast-new')
    with temporary.open('wb') as stream:
        stream.write(data)
        os.fchmod(stream.fileno(), mode)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)

def save(path, data):
    atomic(path, (json.dumps(data, indent=2)+'\n').encode(), 0o600)

def raw_pins():
    result = {}
    with open('/dev/mmcblk0', 'rb', buffering=0) as disk:
        for name, lba, length, expected in (
            ('toc0', 256, 40960, '50537c7ff9d9b20461c0a1181f3b4f04240e63be7aece9f49ba1ce6c18bc0c9b'),
            ('header', 4096, 512, '1e07c2743da3e94c0e6f498b4c7a5203c9f7666e3c66b819f64633eb8742ddbb'),
            ('active', 98304, 15008768, 'c5d306559886e947d702457a92149e4c2e6c41713188bee6bbbdcc22409f0da7'),
            ('fallback', 65536, 15008768, '091ebfe06aa47ca3a4ac7e347838dd6175c575771032e1703e6b7b1480e460e3')):
            disk.seek(lba*512)
            digest = sha(disk.read(length))
            assert digest == expected, name
            result[name] = digest
    return result

def properties(name):
    return dict(v.split('=', 1) for v in run('systemctl', 'show', name,
        '-p', 'Type', '-p', 'DefaultDependencies', '-p', 'NotifyAccess', '-p', 'After', '-p', 'BindsTo',
        '-p', 'RemainAfterExit', '-p', 'Before').splitlines())

if sys.argv[1] == 'restore':
    value = json.loads(state.read_text())
    for name, item in value['files'].items():
        assert sha(Path(name).read_bytes()) == item['installed_sha256'], name
    for name, item in value['files'].items():
        if item['original_sha256'] is None:
            Path(name).unlink()
        else:
            original = (backup/'files'/name.lstrip('/')).read_bytes()
            assert sha(original) == item['original_sha256']
            atomic(name, original, item['mode'])
    run('systemctl', 'daemon-reload')
    value.update(state='original-touch-oneshot-restored', restored_boot_id=boot)
    save(state, value)
    print('SCREEN_FAST_BOOT_ORIGINAL_TOUCH_SEQUENCE_RESTORED', flush=True)
    raise SystemExit(0)

if sys.argv[1] == 'verify':
    value = json.loads(state.read_text())
    assert 'restored' not in value['state']
    for name, item in value['files'].items():
        assert sha(Path(name).read_bytes()) == item['installed_sha256'], name
    assert raw_pins() == value['raw_boot_unchanged']
    p = properties('tzx-touch')
    assert p['Type'] == 'notify' and p['NotifyAccess'] == 'all' and p['DefaultDependencies'] == 'no'
    assert p['RemainAfterExit'] == 'yes' and 'tzx-usb-network.service' not in p['After'].split()
    assert {'systemd-remount-fs.service','systemd-udev-trigger.service','tzx-cpub.service'} <= set(p['After'].split())
    assert 'tzx-touch.service' in properties('tzx-display')['BindsTo'].split()
    assert 'tzx-touch-input-ready.service' in properties('lightdm')['After'].split()
    print('SCREEN_FAST_RAIL_AND_FULL_INPUT_ORDER_PINS_PASS', json.dumps(dict(boot_id=boot, touch=p)), flush=True)
    raise SystemExit(0)

assert not state.exists() and not backup.exists()
assert not run('systemctl','--failed','--plain','--no-legend').strip()
assert run('systemctl','is-active','tzx-touch','tzx-display','lightdm','tzx-cpu-dvfs','tzx-gpu-performance').split() == ['active']*5
original = {name: Path(name).read_bytes() for name in pins}
for name, data in original.items():
    assert sha(data) == pins[name], name
before_raw = raw_pins()
new = {}
text = original[touch_unit].decode()
assert text.count('After=tzx-usb-network.service\n') == text.count('Type=oneshot\n') == 1
text = text.replace('After=tzx-usb-network.service\n', 'DefaultDependencies=no\n'
    'After=systemd-remount-fs.service systemd-udev-trigger.service tzx-cpub.service\n'
    'Conflicts=shutdown.target\nBefore=shutdown.target\n')
text = text.replace('Type=oneshot\n', 'Type=notify\nNotifyAccess=all\n')
new[touch_unit] = text.encode()
text = original[touch_script].decode()
old = '    sleep 1\n    insmod /usr/local/lib/tzx-peripherals-accel1/tzx_gsl3670.ko\n'
assert text.count(old) == 1
text = text.replace(old, '    if test -n "${NOTIFY_SOCKET:-}"; then\n'
    '        /usr/bin/python3 '+helper+' rails\n    fi\n'
    '    sleep 1\n'
    '    insmod /usr/local/lib/tzx-peripherals-accel1/tzx_gsl3670.ko\n')
old = '    trap - EXIT HUP INT TERM\n    echo RUNTIME_TOUCH_DRIVER_BOUND_CLDO2_3V3\n'
assert text.count(old) == 1
text = text.replace(old, '    trap - EXIT HUP INT TERM\n'
    '    if test -n "${NOTIFY_SOCKET:-}"; then\n'
    '        /usr/bin/python3 '+helper+' input\n    fi\n'
    '    echo RUNTIME_TOUCH_DRIVER_BOUND_CLDO2_3V3\n')
assert text.count('rm -f "$state"\n') == 2
text = text.replace('rm -f "$state"\n', 'rm -f "$state" /run/tzx-touch-rail-ready.json /run/tzx-touch-input-ready.json\n')
new[touch_script] = text.encode()
new[helper] = Path('/home/debian/screen_fast_touch_ready.py').read_bytes()
new['/etc/systemd/system/tzx-touch.service.d/99-fast-panel.conf'] = (
    '[Service]\nExecStart=\nExecStart=/usr/bin/timeout --kill-after=2s 22s /bin/sh '+touch_script+' start\n').encode()
new['/etc/systemd/system/tzx-display.service.d/99-touch-lifetime.conf'] = b'[Unit]\nBindsTo=tzx-touch.service\n'
new['/etc/systemd/system/tzx-touch-input-ready.service'] = (
    '[Unit]\nDescription=Wait for complete GSL3670 input before the desktop\n'
    'BindsTo=tzx-touch.service\nAfter=tzx-touch.service\nBefore=lightdm.service\n'
    '[Service]\nType=oneshot\nRemainAfterExit=yes\nTimeoutStartSec=28s\n'
    'ExecStart=/usr/bin/python3 '+helper+' wait\n').encode()
new['/etc/systemd/system/lightdm.service.d/99-touch-complete.conf'] = (
    '[Unit]\nRequires=tzx-touch-input-ready.service\nAfter=tzx-touch-input-ready.service\n').encode()
new['/etc/systemd/system/tzx-video.service.d/99-sid-thermal-order.conf'] = (
    '[Unit]\nRequires=tzx-thermal.service\nAfter=tzx-thermal.service\n').encode()
for name in set(new)-set(original):
    assert not Path(name).exists(), name
backup.mkdir(parents=True)
files = {}
for name, data in new.items():
    mode = (Path(name).stat().st_mode&0o777) if name in original else 0o644
    if name in original:
        atomic(backup/'files'/name.lstrip('/'), original[name], mode)
    files[name] = dict(original_sha256=sha(original[name]) if name in original else None,
                       installed_sha256=sha(data), mode=mode)
atomic(backup/'install_screen_fast_boot.py', Path(__file__).read_bytes(), 0o600)
save(backup/'before.json', dict(boot_id=boot, files=files,
    units={name: run('systemctl','cat',name) for name in ('tzx-touch','tzx-display','lightdm')},
    screen_health=json.loads(Path('/var/lib/tzx/screen-boot-health.json').read_text())))
try:
    for name, data in new.items():
        atomic(name, data, files[name]['mode'])
    verification = run('systemd-analyze', 'verify', '--man=no', 'tzx-touch.service', 'tzx-display.service',
                       'tzx-touch-input-ready.service', 'lightdm.service', 'graphical.target')
    assert 'cycle' not in verification.lower(), verification
    run('systemctl','daemon-reload')
    save(state, dict(state='installed-pending-actual-normal-reboot', installed_boot_id=boot,
        installed_unix=int(time.time()), files=files, raw_boot_unchanged=before_raw,
        backup=str(backup), verification=verification, live_touch_not_restarted=True,
        original_rail_delay_preserved=True, original_firmware_and_input_checks_preserved=True,
        firmware_upload_bounded_seconds=22, desktop_waits_for_complete_input=True))
    run('python3', str(Path(__file__).resolve()), 'verify')
    os.sync()
except BaseException:
    for name in new:
        if name in original:
            atomic(name, original[name], files[name]['mode'])
        else:
            Path(name).unlink(missing_ok=True)
    run('systemctl','daemon-reload')
    state.unlink(missing_ok=True)
    raise
print('SCREEN_FAST_BOOT_RAIL_NOTIFY_INSTALLED_PENDING_REBOOT', json.dumps(files), flush=True)
