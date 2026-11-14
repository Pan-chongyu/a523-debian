"""Read regulator metadata; do not infer board wiring or alter voltages."""
import json
import os
from pathlib import Path

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
rows = []
for regulator in sorted(Path('/sys/class/regulator').glob('regulator.*')):
    row = {'sysfs':str(regulator),'device':str(regulator.resolve())}
    for name in ('name','microvolts','state','status','type','num_users'):
        try:
            row[name] = (regulator/name).read_text().strip()
        except OSError as error:
            row[name] = {'unavailable_errno':error.errno}
    rows.append(row)
devices = []
for device in sorted(Path('/sys/bus/i2c/devices').iterdir()):
    if not (device/'name').is_file():
        continue
    devices.append({'device':device.name,'name':(device/'name').read_text().strip(),
                    'driver':str((device/'driver').resolve()) if (device/'driver').exists() else None})
print('POWER_RAIL_READONLY_SNAPSHOT',json.dumps({'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'regulators':rows,'known_i2c_devices':devices,'voltage_or_enable_written':False,
    'board_rail_wiring_inferred':False}),flush=True)
