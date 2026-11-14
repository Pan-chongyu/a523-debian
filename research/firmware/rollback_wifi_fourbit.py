"""Restore the two owned WLAN files; restart WLAN separately or reboot."""
import hashlib
import os
from pathlib import Path
import json

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
base = Path('/root/tzx-recovery/wifi-fourbit')
before = json.loads((base / 'before.json').read_text())
installed = json.loads((base / 'installed.json').read_text())
assert set(before) == set(installed) == {
    '/usr/local/lib/tzx-peripherals-accel1/tzx_wifi_runtime.ko',
    '/usr/local/lib/tzx-peripherals-accel1/tzx-wifi-runtime-test.sh'}
for name, record in before.items():
    path = Path(name)
    assert not path.is_symlink()
    assert hashlib.sha256(path.read_bytes()).hexdigest() in (record['sha256'], installed[name])
    data = (base / path.name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == record['sha256']
    temporary = path.with_name(path.name + '.onebit-restore')
    temporary.write_bytes(data)
    temporary.chmod(record['mode'])
    temporary.replace(path)
Path('/var/lib/tzx/wifi-fourbit-installed.json').unlink(missing_ok=True)
os.sync()
print('WIFI_ONEBIT_FILES_RESTORED_NETWORK_RESTART_OR_REBOOT_REQUIRED', flush=True)
