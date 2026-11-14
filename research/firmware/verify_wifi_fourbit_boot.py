"""Record boot qualification only after the matching network and file audits."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
record_path = Path('/var/lib/tzx/wifi-fourbit-installed.json')
record = json.loads(record_path.read_text())
assert record['boot_id'] != boot
for name, digest in record['files'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest
for unit, marker in (
    ('tzx-wifi-fourbit-boot-transfer.service', 'WIFI_LOCAL_TRANSFER_AND_SDIO_INTEGRITY_PASS'),
    ('tzx-wifi-fourbit-boot-file-audit.service', 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS')):
    properties = subprocess.check_output(['systemctl', 'show', unit, '-p', 'Result',
                                         '-p', 'ActiveState', '-p', 'ExecMainStatus'], text=True)
    assert all(value in properties for value in ('Result=success\n', 'ExecMainStatus=0\n', 'ActiveState=inactive\n'))
    journal = subprocess.check_output(['journalctl', '-b', '0', '-u', unit, '--no-pager'], text=True)
    assert marker in journal
transfer = json.loads(Path('/home/debian/wifi-transfer-fourbit-boot.json').read_text())
assert transfer['boot_id'] == boot
ios = Path('/sys/kernel/debug/mmc1/ios').read_text()
assert '(4 bits)' in ios and '12000000 Hz' in ios
for unit in ('lightdm', 'tzx-wifi', 'tzx-bluetooth', 'tzx-touch', 'tzx-audio',
             'tzx-battery', 'tzx-thermal', 'tzx-tablet-keys'):
    subprocess.run(['systemctl', 'is-active', '--quiet', unit], check=True)
assert subprocess.check_output(['systemctl', 'is-system-running'], text=True).strip() == 'running'
record.update(state='manual_trials_and_autostart_reboot_verified', verified_boot_id=boot,
              verified_transfer=transfer, desktop_restart_required=False)
record_path.write_text(json.dumps(record, indent=2) + '\n')
os.sync()
print('WIFI_FOURBIT_AUTOSTART_REBOOT_AND_DATA_INTEGRITY_VERIFIED', json.dumps(record), flush=True)
