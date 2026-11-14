"""Package verified UART setup and shared-firmware ordering for periph1."""
import hashlib
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
out = root / 'build/peripheral-kernel'
stage = out / 'bluetooth-runtime'
release = '7.3.3-tzx-a523-periph1'
module = 'lib/modules/' + release + '/extra/tzx_bt_runtime.ko'
files = {module: (out / 'tzx_bt_runtime.ko').read_bytes()}
for name in ('tzx-bt-hardware.service', 'tzx-bluetooth.service'):
    files['etc/systemd/system/' + name] = (root / 'firmware' / name).read_bytes()
files['usr/local/lib/tzx-bluetooth/runtime.py'] = (root / 'firmware/tzx_bluetooth_runtime.py').read_bytes()
files['usr/local/lib/tzx-bluetooth/MODULE.sha256'] = (
    hashlib.sha256(files[module]).hexdigest() + '  /' + module + '\n').encode()
files['etc/systemd/system/tzx-wifi.service.d/20-bluetooth.conf'] = b'''[Unit]
Wants=tzx-bt-hardware.service
After=tzx-bt-hardware.service
'''
# Ensure the BlueZ condition is evaluated after the HCI core has created sysfs.
files['etc/systemd/system/bluetooth.service.d/20-tzx-uart.conf'] = b'''[Unit]
Wants=tzx-bt-hardware.service
After=tzx-bt-hardware.service
'''
files['etc/tmpfiles.d/tzx-desktop.conf'] = b'f /run/utmp 0664 root utmp -\n'
wifi_path = 'usr/local/lib/tzx-peripherals-periph1/tzx-wifi-runtime'
wifi = (out / 'runtime' / wifi_path).read_text()
wifi = wifi.replace('    insmod "$runtime/aic8800_bsp.ko"', '''    # PM2 reset is effective only after the shared chip power/SDIO host is up.
    if test -w /sys/module/tzx_bt_runtime/parameters/prepare_firmware; then
        test ! -d /sys/class/bluetooth/hci0
        echo 1 > /sys/module/tzx_bt_runtime/parameters/prepare_firmware
    fi
    insmod "$runtime/aic8800_bsp.ko"''')
files[wifi_path] = wifi.encode()
manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
for name, data in files.items():
    path = stage / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
(stage / 'FILES.json').write_text(json.dumps(manifest, indent=2) + '\n')
installer = '''import hashlib,json,os,subprocess
from pathlib import Path
assert os.geteuid()==0
assert os.uname().release=='7.3.3-tzx-a523-periph1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
stage=Path(__file__).resolve().parent
files=json.loads((stage/'FILES.json').read_text())
for name,digest in files.items():
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    assert name.startswith(('usr/local/lib/tzx-bluetooth/','usr/local/lib/tzx-peripherals-periph1/','lib/modules/7.3.3-tzx-a523-periph1/extra/','etc/systemd/system/','etc/tmpfiles.d/tzx-'))
    assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==digest
for name,digest in files.items():
    target=Path('/')/name;target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.tzx-new')
    temporary.write_bytes((stage/name).read_bytes());temporary.chmod(0o644);temporary.replace(target)
    assert hashlib.sha256(target.read_bytes()).hexdigest()==digest
subprocess.run(['depmod','-a',os.uname().release],check=True)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemd-analyze','verify','tzx-bt-hardware.service','tzx-bluetooth.service','tzx-wifi.service'],check=True)
subprocess.run(['systemctl','enable','tzx-bt-hardware.service','tzx-bluetooth.service'],check=True)
subprocess.run(['systemd-tmpfiles','--create','/etc/tmpfiles.d/tzx-desktop.conf'],check=True)
os.sync()
print('BLUETOOTH_RUNTIME_INSTALLED_HASH_VERIFIED',len(files))
'''
(stage / 'install.py').write_text(installer, newline='\n')
archive = out / 'bluetooth-runtime.tar.gz'
with tarfile.open(archive, 'w:gz') as package:
    for name in sorted([*files, 'FILES.json', 'install.py']):
        package.add(stage / name, arcname=name, recursive=False)
(out / 'bluetooth-runtime.json').write_text(json.dumps({
    'files': manifest, 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'autostart_reboot_verified': False}, indent=2) + '\n')
print('BLUETOOTH_PACKAGE', len(files), archive.stat().st_size)
