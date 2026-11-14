"""Install only the SDIO host and checked loader after two passing manual loads."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--finish-metadata', action='store_true')
args = parser.parse_args()
assert os.geteuid() == 0 and os.uname().release == '7.3.3-tzx-a523-accel1' and '#4 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert not Path('/sys/module/panfrost').exists()
assert not Path('/run/systemd/system/tzx-wifi.service.d/95-fourbit-test.conf').exists()
unit = 'tzx-wifi-fourbit-trial.service'
properties = subprocess.check_output(['systemctl', 'show', unit, '-p', 'Result',
                                     '-p', 'ActiveState', '-p', 'ExecMainStatus'], text=True)
assert all(value in properties for value in ('Result=success\n', 'ExecMainStatus=0\n', 'ActiveState=inactive\n'))
journal = subprocess.check_output(['journalctl', '-b', '0', '-u', unit, '--no-pager'], text=True)
assert 'WIFI_FOUR_BIT_TWO_LOADS_AND_VERIFIED_LOCAL_TRANSFER_PASS' in journal
assert 'WIFI_BUS_BASELINE_RESTORED' in journal
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
for number in (1, 2):
    record = json.loads(Path('/home/debian/wifi-transfer-fourbit-' + str(number) + '.json').read_text())
    assert record['boot_id'] == boot and len(record['transfers']) == 4
    assert all(row['sha256'] == 'PASS' for row in record['transfers'])
    assert '(4 bits)' in record['mmc_ios'] and '12000000 Hz' in record['mmc_ios']
base = Path('/usr/local/lib/tzx-peripherals-accel1')
host = base / 'tzx_wifi_runtime.ko'
loader = base / 'tzx-wifi-runtime-test.sh'
old_module = '301839a7b0d84bc7093ae13266fd36a593d7e3dd30799fe4db1b22eecbc34073'
new_module = '313e014683a700cf4157eb08f7136b6af12c938464d0e520690a2db72890f74b'
backup = Path('/root/tzx-recovery/wifi-fourbit')
record_path = Path('/var/lib/tzx/wifi-fourbit-installed.json')
record_path.parent.mkdir(parents=True, exist_ok=True)
if args.finish_metadata:
    before = json.loads((backup / 'before.json').read_text())
    installed = json.loads((backup / 'installed.json').read_text())
    assert set(before) == set(installed) == {str(host), str(loader)}
    assert before[str(host)]['sha256'] == old_module
    assert before[str(loader)]['sha256'] == '3a4c7bbb5923c2e10c376cc2579c2754e20919435fa32a9c12934cf82c6f5c56'
    assert installed[str(host)] == new_module
    for path in (host, loader):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == installed[str(path)]
        assert hashlib.sha256((backup / path.name).read_bytes()).hexdigest() == before[str(path)]['sha256']
    assert not record_path.exists()
    record = {'state': 'manual_trials_passed_reboot_pending', 'boot_id': boot,
              'proof_journal_sha256': hashlib.sha256(journal.encode()).hexdigest(), 'files': installed,
              'clock_Hz': 12000000, 'bus_width': 4, 'power_and_boot_bundle_changed': False}
    record_path.write_text(json.dumps(record, indent=2) + '\n')
    os.sync()
    print('WIFI_FOURBIT_METADATA_FINISHED_ALL_FILES_AND_BACKUPS_VERIFIED', json.dumps(record), flush=True)
    raise SystemExit(0)
assert hashlib.sha256(host.read_bytes()).hexdigest() == old_module
assert hashlib.sha256(loader.read_bytes()).hexdigest() == '3a4c7bbb5923c2e10c376cc2579c2754e20919435fa32a9c12934cf82c6f5c56'
candidate = Path('/home/debian/tzx_wifi_runtime-fourbit.ko').read_bytes()
assert hashlib.sha256(candidate).hexdigest() == new_module
text = loader.read_text()
assert text.count(old_module) == 1
text = text.replace(old_module, new_module)
needle = '    insmod ' + str(host) + '\n'
assert text.count(needle) == 1
text = text.replace(needle, needle.rstrip() + ' bus_width=4\n')
subprocess.run(['/bin/sh', '-n'], input=text, text=True, check=True)
backup.mkdir(exist_ok=False)
before = {}
installed = {}
for path, data in ((host, candidate), (loader, text.encode())):
    assert not path.is_symlink()
    saved = backup / path.name
    saved.write_bytes(path.read_bytes())
    before[str(path)] = {'sha256': hashlib.sha256(saved.read_bytes()).hexdigest(),
                         'mode': path.stat().st_mode & 0o777}
    installed[str(path)] = hashlib.sha256(data).hexdigest()
(backup / 'before.json').write_text(json.dumps(before, indent=2) + '\n')
(backup / 'installed.json').write_text(json.dumps(installed, indent=2) + '\n')
(backup / 'rollback.py').write_bytes(Path('/home/debian/rollback_wifi_fourbit.py').read_bytes())
for path, data in ((host, candidate), (loader, text.encode())):
    temporary = path.with_name(path.name + '.fourbit-new')
    temporary.write_bytes(data)
    temporary.chmod(before[str(path)]['mode'])
    temporary.replace(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == installed[str(path)]
record = {'state': 'manual_trials_passed_reboot_pending', 'boot_id': boot,
          'proof_journal_sha256': hashlib.sha256(journal.encode()).hexdigest(), 'files': installed,
          'clock_Hz': 12000000, 'bus_width': 4, 'power_and_boot_bundle_changed': False}
record_path.write_text(json.dumps(record, indent=2) + '\n')
os.sync()
print('WIFI_FOURBIT_INSTALLED_REBOOT_PENDING', json.dumps(record), flush=True)
